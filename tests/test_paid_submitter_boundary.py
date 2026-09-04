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
    camera_plan = {
        "shot_scale": "medium",
        "camera_height": "eye-level",
        "camera_side": "screen-left",
        "axis_relation": "same-side",
        "motion_family": "static",
        "motion_direction": "none",
        "start_framing": "waist-up",
        "end_framing": "waist-up",
        "motivation": "listen to the speaker",
        "lens_intent": "natural perspective",
        "lens_mm": 50,
    }
    protected = {key: value for key, value in camera_plan.items() if key != "lens_mm"}
    request = {
        "prompt": prompt,
        "adapter_id": "nalu.qingshan.minimax-h3",
        "profile_id": "MINIMAX_H3_GIGGLE",
        "model": "MiniMax-H3",
        "provider_model_id": "MiniMax-H3",
        "duration_seconds": 6,
        "combat_or_chase": False,
        "native_resolution_contract": "768p",
        "delivery_resolution_contract": "768p",
        "native_resolution_must_remain_honestly_labeled": True,
        "silent_upscale_forbidden": True,
        "shot_role": "SCENE_FIRST",
        "opening_anchor": {
            "kind": "GENERATED_ENTRY_KEYFRAME",
            "generation_state": "ENTRY_STATE_ONLY",
            "frame_sha256": hashlib.sha256(b"entry-frame").hexdigest(),
        },
        "camera_plan": camera_plan,
        "camera_authority": {
            "selection_mode": "HYBRID",
            "authored_protected_fields": protected,
            "protected_fields_sha256": canonical_sha256(protected),
            "auto_filled_fields": ["lens_mm"],
        },
        "visible_prop_ids": [],
        "prop_state_contracts": [],
        "episode_scene_role": "OTHER_SCENE",
        "shot_state_delta_contract": {
            "mode": "CHANGE",
            "dimensions": [
                {"dimension": "POSITION", "entry": "门外", "exit": "门内"},
            ],
        },
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
        ({"adapter_id": "nalu.qingshan.seedance2-pro"}, "adapter identity"),
        ({"profile_id": "SEEDANCE_2_STANDARD_GIGGLE"}, "profile identity"),
        ({"model": "seedance-2.0-pro"}, "model identity"),
        ({"provider_model_id": "seedance-2.0-pro"}, "provider model identity"),
        ({"duration_seconds": float("nan")}, "numeric duration_seconds"),
        ({"duration_seconds": float("inf")}, "numeric duration_seconds"),
        ({"duration_seconds": 16}, "outside provider limits"),
        ({"combat_or_chase": None}, "explicit combat classification"),
        (
            {"combat_or_chase": False, "combat_choreography_contract": {"beats": ["挥拳"]}},
            "conflicts with noncombat classification",
        ),
        ({"delivery_resolution_contract": "1440p"}, "delivery resolution contract"),
        ({"silent_upscale_forbidden": False}, "forbid silent upscale"),
        ({"shot_role": None}, "explicit shot role"),
        ({"opening_anchor": None}, "opening anchor"),
        (
            {"opening_anchor": {"kind": "GENERATED_ENTRY_KEYFRAME"}},
            "entry state only",
        ),
        (
            {
                "shot_role": "SAME_SCENE_CONTINUATION",
                "opening_anchor": {
                    "kind": "GENERATED_ENTRY_KEYFRAME",
                    "generation_state": "ENTRY_STATE_ONLY",
                    "frame_sha256": "0" * 64,
                },
            },
            "previous accepted final frame",
        ),
        ({"camera_authority": None}, "camera authority"),
        (
            {"camera_plan": {"shot_scale": "close-up"}},
            "missing a protected director field",
        ),
        (
            {
                "camera_authority": {
                    "selection_mode": "LOCKED",
                    "authored_protected_fields": {},
                    "protected_fields_sha256": "0" * 64,
                    "auto_filled_fields": ["lens_mm"],
                }
            },
            "protected director fields were changed",
        ),
        ({"visible_prop_ids": None}, "explicit visible-prop list"),
        ({"visible_prop_ids": ["case"], "prop_state_contracts": []}, "visible-prop order"),
        ({"episode_scene_role": None}, "explicit episode scene role"),
        (
            {
                "episode_scene_role": "FIRST_SCENE",
                "prior_episode_event_relation": "CONTINUING",
                "event_motion_class": "STATIC",
                "writer_authored_continuation_action": "继续奔跑",
            },
            "cannot open as a static tableau",
        ),
        (
            {
                "episode_scene_role": "FIRST_SCENE",
                "prior_episode_event_relation": "CONTINUING",
                "event_motion_class": "RUNNING",
            },
            "writer-authored action",
        ),
        ({"shot_state_delta_contract": None}, "shot state-delta contract"),
        (
            {
                "shot_state_delta_contract": {
                    "mode": "CHANGE",
                    "dimensions": [
                        {"dimension": "POSTURE", "entry": "站立", "exit": "站立"},
                    ],
                }
            },
            "requires a real change",
        ),
        (
            {
                "shot_state_delta_contract": {
                    "mode": "INTENTIONAL_HOLD",
                    "dimensions": [
                        {"dimension": "CONTACT", "entry": "未接触", "exit": "未接触"},
                    ],
                }
            },
            "writer-authored reason",
        ),
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


def test_paid_boundary_rejects_provider_prompt_over_10000_runes_before_transport(
    tmp_path: Path,
) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_paid_prompt_rune_limit")
    transport = IdempotentFakeTransport()

    with pytest.raises(ConflictError, match="exceeds 10000 runes"):
        api.app.state.remote_task_submitter.submit_paid_task(
            run.id,
            task_key="E01-U01",
            provider="giggle",
            model="MiniMax-H3",
            request=paid_request("甲" * 10_001),
            transport=transport,
        )

    assert transport.calls == 0


def test_paid_boundary_accepts_exact_10000_rune_provider_prompt(tmp_path: Path) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_paid_prompt_rune_boundary")
    transport = IdempotentFakeTransport()
    request = paid_request("甲" * 10_000)

    accepted = api.app.state.remote_task_submitter.submit_paid_task(
        run.id,
        task_key="E01-U01",
        provider="giggle",
        model="MiniMax-H3",
        request=request,
        transport=transport,
    )

    assert accepted.state == RemoteTaskState.SUBMITTED
    assert transport.calls == 1


def test_same_scene_continuation_binds_previous_accepted_final_frame(
    tmp_path: Path,
) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_paid_chained_anchor")
    transport = IdempotentFakeTransport()
    request = paid_request(
        "从上一个真实结尾画面继续，不重新生成开场",
        shot_role="SAME_SCENE_CONTINUATION",
        opening_anchor={
            "kind": "PREVIOUS_ACCEPTED_FINAL_FRAME",
            "source_task_id": "provider-task-E01-U01",
            "source_receipt_sha256": hashlib.sha256(b"provider-receipt").hexdigest(),
            "frame_sha256": hashlib.sha256(b"accepted-final-frame").hexdigest(),
        },
    )

    accepted = api.app.state.remote_task_submitter.submit_paid_task(
        run.id,
        task_key="E01-U02",
        provider="giggle",
        model="MiniMax-H3",
        request=request,
        transport=transport,
    )

    assert accepted.state == RemoteTaskState.SUBMITTED
    recorded = transport.accepted[accepted.submission_fingerprint].receipt["request"]
    assert recorded["opening_anchor"] == request["opening_anchor"]


def test_paid_boundary_preserves_director_camera_authority(tmp_path: Path) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_paid_camera_authority")
    transport = IdempotentFakeTransport()
    changed = paid_request("不得发送")
    changed["camera_plan"]["camera_side"] = "screen-right"

    with pytest.raises(ConflictError, match="protected director fields were changed"):
        api.app.state.remote_task_submitter.submit_paid_task(
            run.id,
            task_key="E01-U01",
            provider="giggle",
            model="MiniMax-H3",
            request=changed,
            transport=transport,
        )
    assert transport.calls == 0

    locked = paid_request("锁定导演镜头，不允许自动补写")
    locked["camera_plan"].pop("lens_mm")
    protected = locked["camera_plan"].copy()
    locked["camera_authority"] = {
        "selection_mode": "LOCKED",
        "authored_protected_fields": protected,
        "protected_fields_sha256": canonical_sha256(protected),
        "auto_filled_fields": [],
    }
    accepted = api.app.state.remote_task_submitter.submit_paid_task(
        run.id,
        task_key="E01-U02",
        provider="giggle",
        model="MiniMax-H3",
        request=locked,
        transport=transport,
    )
    assert accepted.state == RemoteTaskState.SUBMITTED


def test_paid_boundary_requires_authorized_visually_confirmed_prop_state(
    tmp_path: Path,
) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_paid_prop_state")
    transport = IdempotentFakeTransport()
    prop_state = {
        "prop_id": "old-suitcase",
        "entry": {
            "owner": "Lin",
            "hand": "left",
            "position": "beside left knee",
            "disposition": "closed",
        },
        "exit": {
            "owner": "Mei",
            "hand": "right",
            "position": "against chest",
            "disposition": "closed",
        },
        "writer_authored_transition": False,
        "start_frame_visual_confirmation": {
            "status": "PASS",
            "frame_sha256": hashlib.sha256(b"confirmed-prop-frame").hexdigest(),
        },
    }
    unauthorized = paid_request(
        "林把旧皮箱交给梅",
        visible_prop_ids=["old-suitcase"],
        prop_state_contracts=[prop_state],
    )

    with pytest.raises(ConflictError, match="ownership change lacks writer authority"):
        api.app.state.remote_task_submitter.submit_paid_task(
            run.id,
            task_key="E01-U01",
            provider="giggle",
            model="MiniMax-H3",
            request=unauthorized,
            transport=transport,
        )
    assert transport.calls == 0

    prop_state["writer_authored_transition"] = True
    authorized = paid_request(
        "林把旧皮箱交给梅",
        visible_prop_ids=["old-suitcase"],
        prop_state_contracts=[prop_state],
    )
    accepted = api.app.state.remote_task_submitter.submit_paid_task(
        run.id,
        task_key="E01-U02",
        provider="giggle",
        model="MiniMax-H3",
        request=authorized,
        transport=transport,
    )
    assert accepted.state == RemoteTaskState.SUBMITTED


def test_first_scene_preserves_active_prior_episode_event(tmp_path: Path) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_paid_prior_event")
    transport = IdempotentFakeTransport()
    request = paid_request(
        "上一集的追赶尚未结束，本集从林叔冲进车站继续",
        episode_scene_role="FIRST_SCENE",
        prior_episode_event_relation="CONTINUING",
        event_motion_class="RUNNING",
        writer_authored_continuation_action="林叔喘着气冲进车站并回头寻找追赶者",
    )

    accepted = api.app.state.remote_task_submitter.submit_paid_task(
        run.id,
        task_key="E02-U01",
        provider="giggle",
        model="MiniMax-H3",
        request=request,
        transport=transport,
    )

    assert accepted.state == RemoteTaskState.SUBMITTED
    recorded = transport.accepted[accepted.submission_fingerprint].receipt["request"]
    assert recorded["prior_episode_event_relation"] == "CONTINUING"


def test_writer_can_authorize_an_intentional_static_hold(tmp_path: Path) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_paid_intentional_hold")
    transport = IdempotentFakeTransport()
    request = paid_request(
        "林叔停在门前，镜头保持不动，让观众听见远处警笛",
        shot_state_delta_contract={
            "mode": "INTENTIONAL_HOLD",
            "dimensions": [
                {"dimension": "POSITION", "entry": "门前", "exit": "门前"},
                {"dimension": "POSTURE", "entry": "站立", "exit": "站立"},
            ],
            "writer_authored_hold_reason": "用静止状态突出逐渐接近的画外警笛",
        },
    )

    accepted = api.app.state.remote_task_submitter.submit_paid_task(
        run.id,
        task_key="E02-U02",
        provider="giggle",
        model="MiniMax-H3",
        request=request,
        transport=transport,
    )

    assert accepted.state == RemoteTaskState.SUBMITTED


def test_only_submitter_source_invokes_paid_transport() -> None:
    runtime_root = Path("services/runtime_api/nalu_runtime")
    callers = {
        path.name
        for path in runtime_root.glob("*.py")
        if ".post_paid_task(" in path.read_text(encoding="utf-8")
    }
    assert callers == {"remote_submitter.py"}
