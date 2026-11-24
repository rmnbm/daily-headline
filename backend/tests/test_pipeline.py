import pytest

from app import cli
from app.config import MissingSettingsError
from app.pipeline import Pipeline, Step, StepFailedError, StepStatus, build_prompt
from app.services.chain import ChainClient
from tests.fakes import make_fake_pipeline


def record_steps():
    events = []
    return events, lambda step, status, error: events.append((step, status, error))


def test_full_run_publishes_metadata_and_updates_contract():
    pipeline = make_fake_pipeline()
    events, on_step = record_steps()

    draft, publication = pipeline.run(date="2026-01-02", on_step=on_step)

    assert draft.headline == "Test Headline"
    assert pipeline.images.prompts == [build_prompt("Test Headline")]
    assert pipeline.storage.files == {"headline_2026-01-02.png": b"image-1"}
    assert pipeline.storage.json["metadata_2026-01-02.json"] == {
        "name": "NYT Daily: 2026-01-02",
        "description": "Test Headline",
        "image": "ipfs://image-headline_2026-01-02.png",
    }
    assert pipeline.contract.uris == [publication.metadata_uri]
    assert publication.tx_hash == "0xabc"
    assert [(s, st) for s, st, _ in events] == [
        (step, status) for step in Step for status in (StepStatus.RUNNING, StepStatus.SUCCEEDED)
    ]


def test_failed_step_stops_the_pipeline():
    pipeline = make_fake_pipeline()
    pipeline.storage.error = RuntimeError("pinata down")
    events, on_step = record_steps()

    with pytest.raises(StepFailedError) as exc:
        pipeline.run(on_step=on_step)

    assert exc.value.step == Step.UPLOAD_IMAGE
    assert events[-1] == (Step.UPLOAD_IMAGE, StepStatus.FAILED, "pinata down")
    assert pipeline.contract.uris == []  # nothing sent on-chain


def test_from_settings_requires_all_keys(settings):
    settings.private_key = None
    with pytest.raises(MissingSettingsError, match="PRIVATE_KEY"):
        Pipeline.from_settings(settings)


def test_from_settings_builds_real_clients_without_network(settings):
    pipeline = Pipeline.from_settings(settings)
    assert isinstance(pipeline.contract, ChainClient)


# --- CLI ---------------------------------------------------------------------


def test_cli_run_succeeds(monkeypatch):
    monkeypatch.setattr(Pipeline, "from_settings", classmethod(lambda cls, s: make_fake_pipeline()))
    assert cli.main(["run"]) == 0


def test_cli_run_fails_cleanly_without_settings(caplog):
    assert cli.main(["run"]) == 1
    assert "Missing required settings" in caplog.text


def test_cli_run_returns_1_when_a_step_fails(monkeypatch):
    pipeline = make_fake_pipeline()
    pipeline.contract.error = RuntimeError("out of gas")
    monkeypatch.setattr(Pipeline, "from_settings", classmethod(lambda cls, s: pipeline))
    assert cli.main(["run"]) == 1


def test_cli_requires_a_command():
    with pytest.raises(SystemExit):
        cli.main([])


def test_cli_serve_starts_uvicorn(monkeypatch, settings, caplog):
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    settings.api_key = None

    assert cli.main(["serve", "--port", "9000"]) == 0
    assert calls[0]["port"] == 9000 and calls[0]["host"] == "127.0.0.1"
    assert "API_KEY is not set" in caplog.text
