from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.models import ProductionRun, RemoteTaskState, RunStatus
from nalu_runtime.repository import ConflictError, utc_now


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))


def _episode(api: TestClient) -> tuple[dict, dict, dict]:
    project = api.post("/v1/projects", json={"title": "远端任务恢复测试"}).json()
    season = api.post(
        f"/v1/projects/{project['id']}/seasons",
        json={"title": "第一季", "season_number": 1},
    ).json()
    episode = api.post(
        f"/v1/seasons/{season['id']}/episodes",
        json={"title": "第一集", "episode_number": 1},
    ).json()
    return project, season, episode


def _save_run(
    api: TestClient,
    project: dict,
    season: dict,
    episode: dict,
    *,
    run_id: str,
    dry_run: bool,
) -> ProductionRun:
    now = utc_now()
    run = ProductionRun(
        id=run_id,
        project_id=project["id"],
        season_id=season["id"],
        episode_id=episode["id"],
        status=RunStatus.PREFLIGHT if dry_run else RunStatus.WAITING_FOR_APPROVAL,
        dry_run=dry_run,
        requested_model="MiniMax-H3",
        estimated_budget_credits=100,
        package_path=str(api.app.state.production.data_root / "fixture-package.json"),
        created_at=now,
        updated_at=now,
    )
    api.app.state.repository.save_run(run)
    return run


def test_remote_binding_rejects_dry_run_and_changed_submission(tmp_path: Path) -> None:
    api = _client(tmp_path)
    project, season, episode = _episode(api)
    repository = api.app.state.repository
    run = _save_run(
        api,
        project,
        season,
        episode,
        run_id="run_dry_binding_fixture",
        dry_run=True,
    )
    with pytest.raises(ConflictError, match="dry runs cannot prepare"):
        repository.prepare_remote_task_binding(
            run.id,
            task_key="E01-U01",
            provider="giggle",
            model="MiniMax-H3",
            submission_fingerprint="a" * 64,
            request_sha256="b" * 64,
        )

    paid = _save_run(
        api,
        project,
        season,
        episode,
        run_id="run_paid_binding_fixture",
        dry_run=False,
    )
    with pytest.raises(ConflictError, match="model does not match"):
        repository.prepare_remote_task_binding(
            paid.id,
            task_key="E01-WRONG-MODEL",
            provider="giggle",
            model="seedance-2.0-pro",
            submission_fingerprint="a" * 64,
            request_sha256="b" * 64,
        )
    first = repository.prepare_remote_task_binding(
        paid.id,
        task_key="E01-U01",
        provider="giggle",
        model="MiniMax-H3",
        submission_fingerprint="a" * 64,
        request_sha256="b" * 64,
    )
    replay = repository.prepare_remote_task_binding(
        paid.id,
        task_key="E01-U01",
        provider="giggle",
        model="MiniMax-H3",
        submission_fingerprint="a" * 64,
        request_sha256="b" * 64,
    )
    assert replay.id == first.id
    progress = api.get(
        f"/v1/episodes/{episode['id']}/production-progress"
    ).json()
    assert progress["stage"] == "provider_submission_prepared"
    assert progress["progress_percent"] == 42
    with pytest.raises(ConflictError, match="different submission inputs"):
        repository.prepare_remote_task_binding(
            paid.id,
            task_key="E01-U01",
            provider="giggle",
            model="MiniMax-H3",
            submission_fingerprint="c" * 64,
            request_sha256="b" * 64,
        )


def test_remote_response_commit_is_crash_safe_and_survives_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _client(tmp_path)
    project, season, episode = _episode(api)
    repository = api.app.state.repository
    run = _save_run(
        api,
        project,
        season,
        episode,
        run_id="run_crash_binding_fixture",
        dry_run=False,
    )
    binding = repository.prepare_remote_task_binding(
        run.id,
        task_key="E01-U01",
        provider="giggle",
        model="MiniMax-H3",
        submission_fingerprint="1" * 64,
        request_sha256="2" * 64,
    )
    original_record_event = repository._record_remote_task_event

    def crash_before_commit(*_args, **_kwargs) -> None:
        raise RuntimeError("simulated crash after binding update")

    monkeypatch.setattr(repository, "_record_remote_task_event", crash_before_commit)
    with pytest.raises(RuntimeError, match="simulated crash"):
        repository.transition_remote_task_binding(
            binding.id,
            target_state=RemoteTaskState.SUBMITTED,
            provider_task_id="giggle-task-001",
            response_sha256="3" * 64,
            receipt={"provider_status": "queued"},
            charge_classification="TASK_ID_BOUND_CHARGE_PENDING",
        )
    rolled_back = repository.get_remote_task_binding(binding.id)
    assert rolled_back.state == RemoteTaskState.PREPARED
    assert rolled_back.provider_task_id is None
    assert [event.event_type for event in repository.list_run_events(run.id)] == [
        "remote_task_prepared"
    ]

    monkeypatch.setattr(repository, "_record_remote_task_event", original_record_event)
    submitted = repository.transition_remote_task_binding(
        binding.id,
        target_state=RemoteTaskState.SUBMITTED,
        provider_task_id="giggle-task-001",
        response_sha256="3" * 64,
        receipt={"provider_status": "queued"},
        charge_classification="TASK_ID_BOUND_CHARGE_PENDING",
    )
    assert submitted.state == RemoteTaskState.SUBMITTED

    restarted = _client(tmp_path)
    recovered = restarted.app.state.repository.get_remote_task_binding(binding.id)
    assert recovered == submitted
    replay = restarted.app.state.repository.transition_remote_task_binding(
        binding.id,
        target_state=RemoteTaskState.SUBMITTED,
        provider_task_id="giggle-task-001",
        response_sha256="3" * 64,
        receipt={"provider_status": "queued"},
        charge_classification="TASK_ID_BOUND_CHARGE_PENDING",
    )
    assert replay == submitted
    submitted_progress = restarted.get(
        f"/v1/episodes/{episode['id']}/production-progress"
    ).json()
    assert submitted_progress["stage"] == "remote_generation"
    assert "不会重复提交" in submitted_progress["explanation"]
    assert [event.event_type for event in restarted.app.state.repository.list_run_events(run.id)] == [
        "remote_task_prepared",
        "remote_task_submitted",
    ]

    with pytest.raises(ConflictError, match="provider task identity"):
        restarted.app.state.repository.transition_remote_task_binding(
            binding.id,
            target_state=RemoteTaskState.COMPLETED,
            provider_task_id="different-provider-task",
            response_sha256="4" * 64,
            result_uri="https://provider.invalid/result.mp4",
            receipt={"provider_status": "completed", "credits": 80},
            charge_classification="EXACT_TASK_ID_STATEMENT_MATCH",
            actual_charged_credits=80,
        )

    completed = restarted.app.state.repository.transition_remote_task_binding(
        binding.id,
        target_state=RemoteTaskState.COMPLETED,
        provider_task_id="giggle-task-001",
        response_sha256="4" * 64,
        result_uri="https://provider.invalid/result.mp4",
        receipt={"provider_status": "completed", "credits": 80},
        charge_classification="EXACT_TASK_ID_STATEMENT_MATCH",
        actual_charged_credits=80,
    )
    assert completed.state == RemoteTaskState.COMPLETED
    assert completed.actual_charged_credits == 80
    completed_progress = restarted.get(
        f"/v1/episodes/{episode['id']}/production-progress"
    ).json()
    assert completed_progress["stage"] == "remote_results_received"
    assert completed_progress["progress_percent"] == 72


def test_remote_binding_classifies_ambiguous_and_duplicate_provider_ids(
    tmp_path: Path,
) -> None:
    api = _client(tmp_path)
    project, season, episode = _episode(api)
    repository = api.app.state.repository
    run = _save_run(
        api,
        project,
        season,
        episode,
        run_id="run_classification_fixture",
        dry_run=False,
    )
    first = repository.prepare_remote_task_binding(
        run.id,
        task_key="E01-U01",
        provider="giggle",
        model="MiniMax-H3",
        submission_fingerprint="5" * 64,
        request_sha256="6" * 64,
    )
    ambiguous = repository.transition_remote_task_binding(
        first.id,
        target_state=RemoteTaskState.AMBIGUOUS_CHARGE,
        response_sha256="7" * 64,
        receipt={"http_status": 504},
        charge_classification="PROVIDER_TIMEOUT_CHARGE_UNKNOWN",
    )
    assert ambiguous.state == RemoteTaskState.AMBIGUOUS_CHARGE
    assert ambiguous.provider_task_id is None
    ambiguous_progress = api.get(
        f"/v1/episodes/{episode['id']}/production-progress"
    ).json()
    assert ambiguous_progress["stage"] == "charge_reconciliation"
    assert ambiguous_progress["can_cancel"] is False
    assert "绝不会自动重复提交" in ambiguous_progress["explanation"]

    reconciled = repository.transition_remote_task_binding(
        first.id,
        target_state=RemoteTaskState.ZERO_CHARGE_FAILED,
        response_sha256="8" * 64,
        receipt={"ledger_matches": 0},
        charge_classification="VERIFIED_ZERO_CHARGE_SAFE_TO_RETRY",
        actual_charged_credits=0,
    )
    assert reconciled.state == RemoteTaskState.ZERO_CHARGE_FAILED
    zero_charge_progress = api.get(
        f"/v1/episodes/{episode['id']}/production-progress"
    ).json()
    assert zero_charge_progress["stage"] == "safe_retry_review"
    assert "零扣费" in zero_charge_progress["explanation"]

    submitted = repository.prepare_remote_task_binding(
        run.id,
        task_key="E01-U02",
        provider="giggle",
        model="MiniMax-H3",
        submission_fingerprint="9" * 64,
        request_sha256="a" * 64,
    )
    repository.transition_remote_task_binding(
        submitted.id,
        target_state=RemoteTaskState.SUBMITTED,
        provider_task_id="giggle-task-shared",
        response_sha256="b" * 64,
        charge_classification="TASK_ID_BOUND_CHARGE_PENDING",
    )
    duplicate = repository.prepare_remote_task_binding(
        run.id,
        task_key="E01-U03",
        provider="giggle",
        model="MiniMax-H3",
        submission_fingerprint="c" * 64,
        request_sha256="d" * 64,
    )
    with pytest.raises(ConflictError, match="provider task ID is already bound"):
        repository.transition_remote_task_binding(
            duplicate.id,
            target_state=RemoteTaskState.SUBMITTED,
            provider_task_id="giggle-task-shared",
            response_sha256="e" * 64,
            charge_classification="TASK_ID_BOUND_CHARGE_PENDING",
        )
    assert repository.get_remote_task_binding(duplicate.id).state == (
        RemoteTaskState.PREPARED
    )
