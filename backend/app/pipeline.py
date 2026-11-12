"""Orchestration of the daily pipeline.

The pipeline is split into two phases so a human can review the AI output
before anything is published:
  - prepare: fetch the headline and generate the image (a `Draft`);
  - publish: pin the image and metadata to IPFS, then update the contract.
The CLI runs both phases back to back. The API can pause between them.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol, TypeVar

from app.config import PIPELINE_SETTINGS, Settings
from app.services.chain import ChainClient
from app.services.image import CloudflareImageGenerator
from app.services.ipfs import PinataClient
from app.services.nyt import NytClient

logger = logging.getLogger(__name__)

T = TypeVar("T")


class Step(StrEnum):
    FETCH_HEADLINE = "fetch_headline"
    GENERATE_IMAGE = "generate_image"
    UPLOAD_IMAGE = "upload_image"
    UPLOAD_METADATA = "upload_metadata"
    UPDATE_CONTRACT = "update_contract"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


# Called on every step transition, e.g. to persist progress in the database.
StepListener = Callable[[Step, StepStatus, str | None], None]


class StepFailedError(RuntimeError):
    def __init__(self, step: Step, cause: Exception) -> None:
        super().__init__(f"Step '{step}' failed: {cause}")
        self.step = step


@dataclass(frozen=True)
class Draft:
    date: str
    headline: str
    prompt: str
    image: bytes


@dataclass(frozen=True)
class Publication:
    image_uri: str
    metadata_uri: str
    tx_hash: str


# What the pipeline needs from each service. The real clients match these
# implicitly, and tests can pass simple fakes.
class HeadlineSource(Protocol):
    def fetch_top_headline(self) -> str: ...


class ImageGenerator(Protocol):
    def generate(self, prompt: str) -> bytes: ...


class FileStorage(Protocol):
    def upload_file(self, content: bytes, filename: str) -> str: ...
    def upload_json(self, data: dict, name: str) -> str: ...


class ContractUpdater(Protocol):
    def update_token_uri(self, token_uri: str) -> str: ...


def build_prompt(headline: str) -> str:
    return f"Professional digital art, newspaper aesthetic for: {headline}"


def today_utc() -> str:
    return datetime.now(UTC).date().isoformat()


def _ignore(step: Step, status: StepStatus, error: str | None) -> None:
    pass


class Pipeline:
    def __init__(
        self,
        headlines: HeadlineSource,
        images: ImageGenerator,
        storage: FileStorage,
        contract: ContractUpdater,
    ) -> None:
        self.headlines = headlines
        self.images = images
        self.storage = storage
        self.contract = contract

    @classmethod
    def from_settings(cls, settings: Settings) -> "Pipeline":
        settings.require(*PIPELINE_SETTINGS)
        return cls(
            headlines=NytClient(settings.nyt_api_key.get_secret_value()),
            images=CloudflareImageGenerator(
                settings.cf_account_id, settings.cf_api_token.get_secret_value()
            ),
            storage=PinataClient(settings.pinata_jwt.get_secret_value()),
            contract=ChainClient(
                settings.rpc_url.get_secret_value(),
                settings.private_key.get_secret_value(),
                settings.contract_address,
            ),
        )

    def _run_step(self, step: Step, on_step: StepListener, fn: Callable[..., T], *args) -> T:
        logger.info("Step %s: running", step)
        on_step(step, StepStatus.RUNNING, None)
        try:
            result = fn(*args)
        except Exception as exc:
            logger.error("Step %s: failed: %s", step, exc)
            on_step(step, StepStatus.FAILED, str(exc))
            raise StepFailedError(step, exc) from exc
        logger.info("Step %s: succeeded", step)
        on_step(step, StepStatus.SUCCEEDED, None)
        return result

    def fetch_headline(self, on_step: StepListener = _ignore) -> str:
        return self._run_step(Step.FETCH_HEADLINE, on_step, self.headlines.fetch_top_headline)

    def generate_image(self, prompt: str, on_step: StepListener = _ignore) -> bytes:
        return self._run_step(Step.GENERATE_IMAGE, on_step, self.images.generate, prompt)

    def prepare(self, date: str, on_step: StepListener = _ignore) -> Draft:
        headline = self.fetch_headline(on_step)
        logger.info("Headline: %r", headline)
        prompt = build_prompt(headline)
        image = self.generate_image(prompt, on_step)
        return Draft(date=date, headline=headline, prompt=prompt, image=image)

    def publish(self, draft: Draft, on_step: StepListener = _ignore) -> Publication:
        image_uri = self._run_step(
            Step.UPLOAD_IMAGE,
            on_step,
            self.storage.upload_file,
            draft.image,
            f"headline_{draft.date}.png",
        )
        metadata = {
            "name": f"NYT Daily: {draft.date}",
            "description": draft.headline,
            "image": image_uri,
        }
        metadata_uri = self._run_step(
            Step.UPLOAD_METADATA,
            on_step,
            self.storage.upload_json,
            metadata,
            f"metadata_{draft.date}.json",
        )
        tx_hash = self._run_step(
            Step.UPDATE_CONTRACT, on_step, self.contract.update_token_uri, metadata_uri
        )
        return Publication(image_uri=image_uri, metadata_uri=metadata_uri, tx_hash=tx_hash)

    def run(
        self, date: str | None = None, on_step: StepListener = _ignore
    ) -> tuple[Draft, Publication]:
        """Run the full pipeline without pausing (used by the daily cron)."""
        draft = self.prepare(date or today_utc(), on_step)
        return draft, self.publish(draft, on_step)
