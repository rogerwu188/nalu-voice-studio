import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.models import ProductionRun, RemoteTaskState, RunStatus
from nalu_runtime.remote_submitter import (
    AmbiguousPaidProviderResponse,
    PaidProviderAcceptance,
)
from nalu_runtime.repository import ConflictError, utc_now


def canonical_sha256(value: dict) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def paid_request(prompt: str, **overrides: object) -> dict:
    request = {
        "prompt": prompt,
        "duration_seconds": 6,
        "combat_or_chase": False,
        "native_resolution_contract": "768p",
        "delivery_resolution_contract": "768p",
        "native_resolution_must_remain_honestly_labeled": True,
        "silent_upscale_forbidden": True,
    }
    request.update(overrides)
    return request


def paid_run(
    api: TestClient,
    tmp_path: Path,
    *,
    run_id: str,
    approved: bool = True,
) -> ProductionRun:
    project = api.post("/v1/projects", json={"title": "付费边界测试"}).json()
    season = api.post(
        f"/v1/projects/{project['id']}/seasons",
        json={"title": "第一季", "season_number": 1},
    ).json()
    episode = api.post(
        f"/v1/seasons/{season['id']}/episodes",
        json={"title": "第一集", "episode_number": 1},
    ).json()
    package_body = {
        "schema_version": "nalu.production-package/v1",
        "production_policy": {
            "requested_model": "MiniMax-H3",
            "paid_generation_approved": approved,
            "approved_by": "QA 授权人" if approved else None,
        },
    }
    package = {**package_body, "package_sha256": canonical_sha256(package_body)}
    package_path = tmp_path / f"{run_id}-production-package.json"
    package_path.write_text(
        json.dumps(package, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    now = utc_now()
    run = ProductionRun(
        id=run_id,
        project_id=project["id"],
        season_id=season["id"],
        episode_id=episode["id"],
        status=RunStatus.WAITING_FOR_APPROVAL,
        dry_run=False,
        requested_model="MiniMax-H3",
        estimated_budget_credits=100,
        package_path=str(package_path),
        created_at=now,
        updated_at=now,
    )
    api.app.state.repository.save_run(run)
    return run


class IdempotentFakeTransport:
    provider_name = "giggle"
    supports_idempotency = True

    def __init__(self) -> None:
        self.calls = 0
        self.charges = 0
        self.accepted: dict[str, PaidProviderAcceptance] = {}

    def post_paid_task(
        self, *, request: dict, idempotency_key: str
    ) -> PaidProviderAcceptance:
        self.calls += 1
        if idempotency_key not in self.accepted:
            self.charges += 1
            self.accepted[idempotency_key] = PaidProviderAcceptance(
                provider_task_id="fake-task-001",
                receipt={"provider_status": "queued", "request": request},
            )
        return self.accepted[idempotency_key]


class AmbiguousFakeTransport:
    provider_name = "giggle"
    supports_idempotency = True

    def __init__(self) -> None:
        self.calls = 0

    def post_paid_task(
        self, *, request: dict, idempotency_key: str
    ) -> PaidProviderAcceptance:
        self.calls += 1
        raise AmbiguousPaidProviderResponse(
            "PROVIDER_TIMEOUT_CHARGE_UNKNOWN",
            {"timeout": True, "idempotency_key": idempotency_key},
        )


def test_provider_acceptance_survives_crash_without_duplicate_charge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_paid_crash_boundary")
    submitter = api.app.state.remote_task_submitter
    transport = IdempotentFakeTransport()
    original_record_response = submitter.record_response

    def crash_before_response_commit(*_args, **_kwargs):
        raise RuntimeError("simulated crash after provider acceptance")

    monkeypatch.setattr(submitter, "record_response", crash_before_response_commit)
    with pytest.raises(RuntimeError, match="after provider acceptance"):
        submitter.submit_paid_task(
            run.id,
            task_key="E01-U01",
            provider="giggle",
            model="MiniMax-H3",
            request=paid_request("离线测试，不发送"),
            transport=transport,
        )
    binding = api.app.state.repository.list_remote_task_bindings(run.id)[0]
    assert binding.state == RemoteTaskState.PREPARED
    assert transport.calls == 1
    assert transport.charges == 1

    monkeypatch.setattr(submitter, "record_response", original_record_response)
    recovered = submitter.submit_paid_task(
        run.id,
        task_key="E01-U01",
        provider="giggle",
        model="MiniMax-H3",
        request=paid_request("离线测试，不发送"),
        transport=transport,
    )
    assert recovered.state == RemoteTaskState.SUBMITTED
    assert recovered.provider_task_id == "fake-task-001"
    assert transport.calls == 2
    assert transport.charges == 1


def test_ambiguous_response_is_quarantined_and_never_auto_reposted(
    tmp_path: Path,
) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_paid_ambiguous_boundary")
    submitter = api.app.state.remote_task_submitter
    transport = AmbiguousFakeTransport()

    first = submitter.submit_paid_task(
        run.id,
        task_key="E01-U01",
        provider="giggle",
        model="MiniMax-H3",
        request=paid_request("离线超时测试"),
        transport=transport,
    )
    replay = submitter.submit_paid_task(
        run.id,
        task_key="E01-U01",
        provider="giggle",
        model="MiniMax-H3",
        request=paid_request("离线超时测试"),
        transport=transport,
    )
    assert first.state == RemoteTaskState.AMBIGUOUS_CHARGE
    assert replay == first
    assert transport.calls == 1


def test_paid_boundary_revalidates_package_approval_and_transport_guarantees(
    tmp_path: Path,
) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run = paid_run(
        api,
        tmp_path,
        run_id="run_paid_missing_approval",
        approved=False,
    )
    transport = IdempotentFakeTransport()
    with pytest.raises(ConflictError, match="explicit package-bound approval"):
        api.app.state.remote_task_submitter.submit_paid_task(
            run.id,
            task_key="E01-U01",
            provider="giggle",
            model="MiniMax-H3",
            request=paid_request("不得发送"),
            transport=transport,
        )
    assert transport.calls == 0

    authorized = paid_run(api, tmp_path, run_id="run_paid_no_idempotency")
    transport.supports_idempotency = False
    with pytest.raises(ConflictError, match="must guarantee provider idempotency"):
        api.app.state.remote_task_submitter.submit_paid_task(
            authorized.id,
            task_key="E01-U01",
            provider="giggle",
            model="MiniMax-H3",
            request=paid_request("不得发送"),
            transport=transport,
        )
    assert transport.calls == 0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"duration_seconds": None}, "numeric duration_seconds"),
        ({"duration_seconds": 16}, "outside provider limits"),
        ({"combat_or_chase": None}, "explicit combat classification"),
        (
            {"combat_or_chase": False, "combat_choreography_contract": {"beats": ["挥拳"]}},
            "conflicts with noncombat classification",
        ),
        ({"delivery_resolution_contract": "1440p"}, "delivery resolution contract"),
        ({"silent_upscale_forbidden": False}, "forbid silent upscale"),
    ],
)
def test_paid_boundary_rejects_semantic_contract_loss_before_transport(
    tmp_path: Path, overrides: dict, message: str
) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_paid_semantic_contract")
    transport = IdempotentFakeTransport()

    with pytest.raises(ConflictError, match=message):
        api.app.state.remote_task_submitter.submit_paid_task(
            run.id,
            task_key="E01-U01",
            provider="giggle",
            model="MiniMax-H3",
            request=paid_request("不得发送", **overrides),
            transport=transport,
        )
    assert transport.calls == 0


def test_explicit_noncombat_remains_noncombat_despite_negative_prompt_words(
    tmp_path: Path,
) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_paid_explicit_noncombat")
    transport = IdempotentFakeTransport()
    request = paid_request(
        "普通家庭对话",
        negative_prompt="禁止打斗、追逐和战斗化表演",
        combat_or_chase=False,
    )

    accepted = api.app.state.remote_task_submitter.submit_paid_task(
        run.id,
        task_key="E01-U01",
        provider="giggle",
        model="MiniMax-H3",
        request=request,
        transport=transport,
    )

    assert accepted.state == RemoteTaskState.SUBMITTED
    assert transport.accepted[accepted.submission_fingerprint].receipt["request"] == request


def test_only_submitter_source_invokes_paid_transport() -> None:
    runtime_root = Path("services/runtime_api/nalu_runtime")
    callers = {
        path.name
        for path in runtime_root.glob("*.py")
        if ".post_paid_task(" in path.read_text(encoding="utf-8")
    }
    assert callers == {"remote_submitter.py"}
