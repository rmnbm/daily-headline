from app.db import RunRepository, RunStatus
from app.pipeline import Draft, Publication, Step, StepStatus


def test_new_run_has_every_step_pending(tmp_path):
    repo = RunRepository(tmp_path / "nested" / "runs.db")  # parent dir is created

    run = repo.get_run(repo.create_run("2026-01-02"))

    assert run.status == RunStatus.PREPARING
    assert run.date == "2026-01-02"
    assert not run.has_image
    assert [(s.step, s.status) for s in run.steps] == [(s, StepStatus.PENDING) for s in Step]


def test_draft_then_publication_round_trip(tmp_path):
    repo = RunRepository(tmp_path / "runs.db")
    run_id = repo.create_run("2026-01-02")

    repo.record_step(run_id, Step.FETCH_HEADLINE, StepStatus.SUCCEEDED, None)
    repo.save_draft(run_id, Draft("2026-01-02", "Headline", "Prompt", b"png"))
    assert repo.get_draft(run_id) == Draft("2026-01-02", "Headline", "Prompt", b"png")

    assert repo.transition(run_id, RunStatus.DRAFT, RunStatus.PUBLISHING)
    repo.save_publication(run_id, Publication("ipfs://img", "ipfs://meta", "0xabc"))

    run = repo.get_run(run_id)
    assert run.status == RunStatus.PUBLISHED
    assert (run.headline, run.has_image, run.tx_hash) == ("Headline", True, "0xabc")
    assert run.steps[0].status == StepStatus.SUCCEEDED


def test_transition_refuses_unexpected_state(tmp_path):
    repo = RunRepository(tmp_path / "runs.db")
    run_id = repo.create_run("2026-01-02")

    assert not repo.transition(run_id, RunStatus.DRAFT, RunStatus.PUBLISHING)
    assert repo.get_run(run_id).status == RunStatus.PREPARING


def test_missing_run_and_listing(tmp_path):
    repo = RunRepository(tmp_path / "runs.db")
    first = repo.create_run("2026-01-01")
    second = repo.create_run("2026-01-02")
    repo.mark_failed(first, "boom")

    assert repo.get_run(999) is None
    assert repo.get_draft(999) is None
    assert repo.get_draft(first) is None  # no image yet
    runs = repo.list_runs()
    assert [r.id for r in runs] == [second, first]  # newest first
    assert runs[1].status == RunStatus.FAILED and runs[1].error == "boom"
    assert [r.id for r in repo.list_runs(limit=1)] == [second]
