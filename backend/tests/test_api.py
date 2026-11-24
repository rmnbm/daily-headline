import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.pipeline import Step, StepStatus
from tests.fakes import make_fake_pipeline

AUTH = {"X-API-Key": "test-api-key"}


@pytest.fixture
def pipeline():
    return make_fake_pipeline()


@pytest.fixture
def client(settings, pipeline):
    return TestClient(create_app(settings, pipeline_factory=lambda: pipeline))


def create_draft(client) -> dict:
    response = client.post("/runs", json={"date": "2026-01-02"}, headers=AUTH)
    assert response.status_code == 201, response.text
    return response.json()


# --- Auth --------------------------------------------------------------------------


def test_health_is_public(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_protected_endpoints_require_the_api_key(client, headers):
    assert client.get("/runs", headers=headers).status_code == 401


def test_api_refuses_requests_when_no_key_is_configured(settings, pipeline):
    settings.api_key = None
    client = TestClient(create_app(settings, pipeline_factory=lambda: pipeline))
    assert client.get("/runs", headers=AUTH).status_code == 503


def test_missing_pipeline_settings_return_503(settings):
    settings.pinata_jwt = None
    client = TestClient(create_app(settings))  # real factory
    response = client.post("/runs", headers=AUTH)
    assert response.status_code == 503
    assert "PINATA_JWT" in response.json()["detail"]


# --- Review flow ------------------------------------------------------------------


def test_create_run_produces_a_draft_without_publishing(client, pipeline):
    run = create_draft(client)

    assert run["status"] == "draft"
    assert run["headline"] == "Test Headline"
    assert run["image_url"] == f"/runs/{run['id']}/image"
    statuses = {s["step"]: s["status"] for s in run["steps"]}
    assert statuses[Step.GENERATE_IMAGE] == StepStatus.SUCCEEDED
    assert statuses[Step.UPDATE_CONTRACT] == StepStatus.PENDING
    assert pipeline.storage.files == {} and pipeline.contract.uris == []


def test_create_run_defaults_to_today(client):
    response = client.post("/runs", headers=AUTH)
    assert response.status_code == 201
    assert len(response.json()["date"]) == 10


def test_draft_image_can_be_downloaded(client):
    run = create_draft(client)
    response = client.get(run["image_url"], headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == b"image-1"


def test_publish_a_draft(client, pipeline):
    run = create_draft(client)

    response = client.post(f"/runs/{run['id']}/publish", headers=AUTH)

    assert response.status_code == 200
    published = response.json()
    assert published["status"] == "published"
    assert published["tx_hash"] == "0xabc"
    assert pipeline.contract.uris == [published["metadata_uri"]]
    assert all(s["status"] == StepStatus.SUCCEEDED for s in published["steps"])


def test_a_draft_cannot_be_published_twice(client, pipeline):
    run = create_draft(client)
    client.post(f"/runs/{run['id']}/publish", headers=AUTH)

    response = client.post(f"/runs/{run['id']}/publish", headers=AUTH)

    assert response.status_code == 409
    assert len(pipeline.contract.uris) == 1


def test_rejected_draft_cannot_be_published(client, pipeline):
    run = create_draft(client)

    assert client.post(f"/runs/{run['id']}/reject", headers=AUTH).json()["status"] == "rejected"
    assert client.post(f"/runs/{run['id']}/publish", headers=AUTH).status_code == 409
    assert client.post(f"/runs/{run['id']}/reject", headers=AUTH).status_code == 409
    assert pipeline.contract.uris == []


def test_list_and_get_runs(client):
    first, second = create_draft(client), create_draft(client)

    listed = client.get("/runs", headers=AUTH).json()
    assert [r["id"] for r in listed] == [second["id"], first["id"]]
    assert client.get(f"/runs/{first['id']}", headers=AUTH).json()["headline"] == "Test Headline"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/runs/999"),
        ("get", "/runs/999/image"),
        ("post", "/runs/999/publish"),
        ("post", "/runs/999/reject"),
    ],
)
def test_unknown_run_returns_404(client, method, path):
    assert getattr(client, method)(path, headers=AUTH).status_code == 404


# --- Failures --------------------------------------------------------------------


def test_failed_preparation_is_recorded(client, pipeline):
    pipeline.images.error = RuntimeError("cloudflare down")

    response = client.post("/runs", headers=AUTH)

    assert response.status_code == 502
    run_id = response.json()["detail"]["run_id"]
    run = client.get(f"/runs/{run_id}", headers=AUTH).json()
    assert run["status"] == "failed"
    assert "cloudflare down" in run["error"]
    assert run["image_url"] is None
    assert client.get(f"/runs/{run_id}/image", headers=AUTH).status_code == 404


def test_failed_publication_is_recorded(client, pipeline):
    run = create_draft(client)
    pipeline.contract.error = RuntimeError("out of gas")

    response = client.post(f"/runs/{run['id']}/publish", headers=AUTH)

    assert response.status_code == 502
    failed = client.get(f"/runs/{run['id']}", headers=AUTH).json()
    assert failed["status"] == "failed"
    steps = {s["step"]: s for s in failed["steps"]}
    assert steps[Step.UPDATE_CONTRACT]["status"] == StepStatus.FAILED
    assert steps[Step.UPDATE_CONTRACT]["error"] == "out of gas"
