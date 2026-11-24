"""HTTP API to prepare, review and publish the daily NFT.

Flow: `POST /runs` fetches the headline and generates the image (a draft),
a human checks it with `GET /runs/{id}` and `GET /runs/{id}/image`, then
calls `POST /runs/{id}/publish` or `POST /runs/{id}/reject`.

Every endpoint except `/health` requires the `X-API-Key` header. If `API_KEY`
is not configured, the protected endpoints answer 503 instead of being open.

Run with: python -m app.cli serve
"""

import logging
import secrets
from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

from app.config import MissingSettingsError, Settings, get_settings
from app.db import RunRecord, RunRepository, RunStatus
from app.pipeline import Pipeline, StepFailedError, today_utc

logger = logging.getLogger(__name__)

PipelineFactory = Callable[[], Pipeline]


# --- Response models -------------------------------------------------------------


class StepOut(BaseModel):
    step: str
    status: str
    error: str | None
    updated_at: str


class RunOut(BaseModel):
    id: int
    date: str
    status: RunStatus
    headline: str | None
    prompt: str | None
    image_url: str | None
    image_uri: str | None
    metadata_uri: str | None
    tx_hash: str | None
    error: str | None
    created_at: str
    updated_at: str
    steps: list[StepOut]

    @classmethod
    def from_record(cls, run: RunRecord) -> "RunOut":
        return cls(
            id=run.id,
            date=run.date,
            status=run.status,
            headline=run.headline,
            prompt=run.prompt,
            image_url=f"/runs/{run.id}/image" if run.has_image else None,
            image_uri=run.image_uri,
            metadata_uri=run.metadata_uri,
            tx_hash=run.tx_hash,
            error=run.error,
            created_at=run.created_at,
            updated_at=run.updated_at,
            steps=[StepOut(**vars(step)) for step in run.steps],
        )


class CreateRunIn(BaseModel):
    date: str | None = None


# --- App -------------------------------------------------------------------------


def create_app(
    settings: Settings | None = None, pipeline_factory: PipelineFactory | None = None
) -> FastAPI:
    settings = settings or get_settings()
    repo = RunRepository(settings.database_path)
    build_pipeline = pipeline_factory or (lambda: Pipeline.from_settings(settings))

    api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

    def require_api_key(key: Annotated[str | None, Depends(api_key_header)]) -> None:
        expected = settings.api_key.get_secret_value() if settings.api_key else ""
        if not expected:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "API_KEY is not configured")
        if not key or not secrets.compare_digest(key.encode(), expected.encode()):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")

    def get_pipeline() -> Pipeline:
        try:
            return build_pipeline()
        except MissingSettingsError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    def load_run(run_id: int) -> RunRecord:
        run = repo.get_run(run_id)
        if run is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Run {run_id} not found")
        return run

    def recorder(run_id: int):
        return lambda step, step_status, error: repo.record_step(run_id, step, step_status, error)

    app = FastAPI(title="Daily Headline NFT", version="1.0.0")
    auth = [Depends(require_api_key)]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/runs", status_code=status.HTTP_201_CREATED, dependencies=auth)
    def create_run(
        pipeline: Annotated[Pipeline, Depends(get_pipeline)], body: CreateRunIn | None = None
    ) -> RunOut:
        """Fetch today's headline and generate the image. Nothing is published yet."""
        run_id = repo.create_run((body and body.date) or today_utc())
        run = repo.get_run(run_id)
        try:
            draft = pipeline.prepare(run.date, on_step=recorder(run_id))
        except StepFailedError as exc:
            repo.mark_failed(run_id, str(exc))
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, {"run_id": run_id, "error": str(exc)}
            ) from exc
        repo.save_draft(run_id, draft)
        return RunOut.from_record(load_run(run_id))

    @app.get("/runs", dependencies=auth)
    def list_runs(limit: Annotated[int, Query(ge=1, le=200)] = 50) -> list[RunOut]:
        return [RunOut.from_record(run) for run in repo.list_runs(limit)]

    @app.get("/runs/{run_id}", dependencies=auth)
    def get_run(run_id: int) -> RunOut:
        return RunOut.from_record(load_run(run_id))

    @app.get(
        "/runs/{run_id}/image",
        dependencies=auth,
        response_class=Response,
        responses={200: {"content": {"image/png": {}}}},
    )
    def get_image(run_id: int) -> Response:
        load_run(run_id)
        draft = repo.get_draft(run_id)
        if draft is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Run {run_id} has no image")
        return Response(content=draft.image, media_type="image/png")

    @app.post("/runs/{run_id}/publish", dependencies=auth)
    def publish_run(run_id: int, pipeline: Annotated[Pipeline, Depends(get_pipeline)]) -> RunOut:
        """Pin the draft to IPFS and update the contract's token URI."""
        run = load_run(run_id)
        if not repo.transition(run_id, RunStatus.DRAFT, RunStatus.PUBLISHING):
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Run {run_id} is {run.status}, not {RunStatus.DRAFT}"
            )
        draft = repo.get_draft(run_id)
        try:
            publication = pipeline.publish(draft, on_step=recorder(run_id))
        except StepFailedError as exc:
            repo.mark_failed(run_id, str(exc))
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY, {"run_id": run_id, "error": str(exc)}
            ) from exc
        repo.save_publication(run_id, publication)
        logger.info("Run %s published (tx %s)", run_id, publication.tx_hash)
        return RunOut.from_record(load_run(run_id))

    @app.post("/runs/{run_id}/reject", dependencies=auth)
    def reject_run(run_id: int) -> RunOut:
        run = load_run(run_id)
        if not repo.transition(run_id, RunStatus.DRAFT, RunStatus.REJECTED):
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Run {run_id} is {run.status}, not {RunStatus.DRAFT}"
            )
        return RunOut.from_record(load_run(run_id))

    return app
