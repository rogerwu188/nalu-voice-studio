import base64
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import av
import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.models import ProductionRun, RemoteTaskState, RunStatus
from nalu_runtime.qingshan_compilers import ModelCompilerRegistry
from nalu_runtime.remote_submitter import (
    AmbiguousPaidProviderResponse,
    PaidProviderAcceptance,
)
from nalu_runtime.repository import ConflictError, utc_now


@pytest.mark.parametrize("reason", ["dry_run", "cancelled", "archived", "child", "newer", "corrupt"])
def test_budget_reservation_rejects_ineligible_or_changed_local_state(tmp_path, reason):
    api = TestClient(create_app(tmp_path / "budget.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_budget_guards")
    repository = api.app.state.repository
    # Deliberately synthetic record: isolates reservation guards, not frame/shot QA.
    record = {"task_key": "E01-U01", "request": {"fixture": True},
              "request_sha256": canonical_sha256({"fixture": True}),
              "production_package_sha256": PAID_PACKAGE_SHA256}
    record["preparation_sha256"] = canonical_sha256(record)
    prepared = repository.append_run_event(run.id, "video_task_prepared", payload=record)
    with repository.db.connect() as db:
        if reason == "dry_run":
            db.execute("UPDATE production_runs SET dry_run = 1 WHERE id = ?", (run.id,))
        elif reason == "cancelled":
            db.execute("UPDATE production_runs SET status = 'cancelled' WHERE id = ?", (run.id,))
        elif reason == "archived":
            db.execute("UPDATE projects SET archived_at = ? WHERE id = ?", (utc_now(), run.project_id))
        elif reason == "child":
            db.execute("UPDATE projects SET audience_mode = 'child' WHERE id = ?", (run.project_id,))
    if reason == "newer":
        repository.append_run_event(run.id, "video_task_prepared", payload={
            **record, "preparation_sha256": "b" * 64})
    if reason == "corrupt":
        repository.append_run_event(run.id, "video_estimate_reserved", payload={
            "task_key": "E01-U02", "estimated_credits": -100, "reservation_sha256": "b" * 64})
    endpoint = f"/v1/production-runs/{run.id}/video-task-preparations/{prepared.id}/estimate-approvals"
    approval = {"preparation_sha256": record["preparation_sha256"], "estimated_credits": 20,
                "confirmed_run_budget_credits": 100, "approved_by": "QA", "confirmation": "fixture only"}
    assert api.post(endpoint, json=approval).status_code == 409
    if reason == "child":
        assert api.post(endpoint, json={**approval, "guardian_approval": True}).status_code == 200


@pytest.mark.parametrize("invalid", [None, "bytes", "hash", "extra_reference", "package", "cancelled", "ratio"])
def test_prepare_concrete_shot_and_image_without_network(tmp_path, invalid):
    api = TestClient(create_app(tmp_path / "prepare.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_frame_fixture", model="seedance-2.0-pro")
    output = io.BytesIO()
    with av.open(output, mode="w", format="image2pipe") as container:
        stream = container.add_stream("png", rate=1)
        stream.width, stream.height, stream.pix_fmt = 16, 16, "rgb24"
        for packet in stream.encode(av.VideoFrame.from_ndarray(np.zeros((16, 16, 3), dtype=np.uint8), format="rgb24")):
            container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    frame = output.getvalue() if invalid != "bytes" else b"not-an-image"
    request = paid_request("合成空房间镜头")
    request.update({"model": "seedance-2.0-pro", "provider_model_id": "seedance-2.0-pro",
                    "adapter_id": "nalu.qingshan.seedance2-pro", "profile_id": "SEEDANCE_2_STANDARD_GIGGLE",
                    "native_resolution_contract": "720p", "delivery_resolution_contract": "720p",
                    "video_transport": {"mode": "image_to_video_start_frame", "aspect_ratio": "1:1",
                                        "start_frame": {"base64": base64.b64encode(frame).decode()}}})
    request["opening_anchor"]["frame_sha256"] = hashlib.sha256(frame).hexdigest()
    request["provider_scope_projection"]["production_package_sha256"] = json.loads(
        Path(run.package_path).read_text())["package_sha256"]
    if invalid == "hash":
        request["opening_anchor"]["frame_sha256"] = "0" * 64
    if invalid == "ratio":
        request["video_transport"]["aspect_ratio"] = "16:9"
    if invalid == "extra_reference":
        request["images"] = [{"url": "https://example.org/reference.png"}]
    if invalid == "package":
        request["provider_scope_projection"]["production_package_sha256"] = "0" * 64
    if invalid == "cancelled":
        api.post(f"/v1/production-runs/{run.id}/cancel", json={"requested_by": "qa", "reason": "fixture"})
    endpoint = f"/v1/production-runs/{run.id}/video-task-preparations"
    response = api.post(endpoint, json={"task_key": "E01-U01", "request": request})
    if invalid:
        assert response.status_code == 409, response.text
        assert not any(e.event_type == "video_task_prepared" for e in api.app.state.repository.list_run_events(run.id))
        return
    assert response.status_code == 200, response.text
    record = response.json()["payload"]
    assert record["request"] == request
    assert record["frame"]["width"] == 16
    assert record["paid_approved"] is False
    assert record["generation_performed"] is False
    assert record["visual_semantics_verified"] is False
    assert api.post(endpoint, json={"task_key": "E01-U01", "request": request}).json()["id"] == response.json()["id"]
    assert api.app.state.repository.list_remote_task_bindings(run.id) == []
    restarted = TestClient(create_app(tmp_path / "prepare.sqlite3", tmp_path / "data"))
    assert restarted.get(f"/v1/production-runs/{run.id}/events").json()[-1]["payload"] == record
    approval_url = endpoint + f"/{response.json()['id']}/estimate-approvals"
    approval = {"preparation_sha256": record["preparation_sha256"], "estimated_credits": 60,
                "confirmed_run_budget_credits": 100, "approved_by": "QA",
                "confirmation": "仅合成预算测试，同意此镜头的预估额度"}
    for patch in ({"preparation_sha256": "0" * 64}, {"confirmed_run_budget_credits": 101}):
        assert api.post(approval_url, json={**approval, **patch}).status_code == 409
    for patch in ({"estimated_credits": True}, {"estimated_credits": -1}, {"approved_by": "   "}):
        assert api.post(approval_url, json={**approval, **patch}).status_code == 422
    reserved = api.post(approval_url, json=approval)
    assert reserved.status_code == 200, reserved.text
    assert api.post(approval_url, json=approval).json()["id"] == reserved.json()["id"]
    assert reserved.json()["payload"]["provider_price_verified"] is False
    assert api.post(approval_url, json={**approval, "estimated_credits": 61}).status_code == 409
    prepared_others = [api.post(endpoint, json={"task_key": key, "request": request}).json()
                       for key in ("E01-U02", "E01-U03")]
    def approve_other(item):
        return api.post(endpoint + f"/{item['id']}/estimate-approvals", json={
            **approval, "preparation_sha256": item["payload"]["preparation_sha256"], "estimated_credits": 40,
        }).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(approve_other, prepared_others)) == [200, 409]
    reservations = [e for e in restarted.get(f"/v1/production-runs/{run.id}/events").json()
                    if e["event_type"] == "video_estimate_reserved"]
    assert sum(e["payload"]["estimated_credits"] for e in reservations) == 100
    assert api.app.state.repository.list_remote_task_bindings(run.id) == []


@pytest.mark.parametrize("status,stage,percent", [
    ("completed", "provider_output_pending_qa", 60),
    ("processing", "remote_generation", 55),
    ("pending", "remote_generation", 55),
    ("failed", "provider_failure_review", 55),
    ("error", "provider_failure_review", 55),
])
def test_saved_task_refresh_uses_bound_id_and_preserves_charge_state(tmp_path, status, stage, percent):
    calls = []
    def serve(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.url.params["task_id"] == "fake-task-001"
        return httpx.Response(200, json={"code": 200, "data": {
            "status": status, "urls": ["https://example.org/fixture.mp4"]}})
    database = tmp_path / "refresh.sqlite3"
    api = TestClient(create_app(database, tmp_path / "data", task_query_http_transport=httpx.MockTransport(serve)))
    run = paid_run(api, tmp_path, run_id="run_query_fixture")
    binding = api.app.state.remote_task_submitter.submit_paid_task(run.id,
        task_key="E01-U01", provider="giggle", model="MiniMax-H3",
        request=paid_request("合成查询"), transport=IdempotentFakeTransport())
    endpoint = f"/v1/production-runs/{run.id}/tasks/{binding.id}/refresh"
    headers = {"X-Nalu-Provider-Key": "fixture-secret"}
    assert api.post(endpoint).status_code == 403
    assert api.post(endpoint, headers={**headers, "Origin": "https://untrusted.invalid"}).status_code == 403
    other = paid_run(api, tmp_path, run_id="run_other_fixture")
    assert api.post(f"/v1/production-runs/{other.id}/tasks/{binding.id}/refresh", headers=headers).status_code == 409
    assert calls == []
    first = api.post(endpoint, headers=headers)
    assert first.status_code == 200, first.text
    assert api.post(endpoint, headers=headers).json()["id"] == first.json()["id"]
    payload = first.json()["payload"]
    assert payload["status"] == status
    assert payload["billing_verified"] is False
    assert payload["master_accepted"] is False
    assert "fixture-secret" not in first.text
    assert api.app.state.repository.get_remote_task_binding(binding.id) == binding
    progress = api.get(f"/v1/episodes/{run.episode_id}/production-progress").json()
    assert progress["stage"] == stage
    assert progress["progress_percent"] == percent
    assert len(calls) == 2
    restarted = TestClient(create_app(database, tmp_path / "data"))
    events = restarted.get(f"/v1/production-runs/{run.id}/events").json()
    assert any(event["id"] == first.json()["id"] for event in events)


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


@pytest.mark.parametrize("crash", [False, True])
def test_single_attempt_transport_records_before_io_and_never_resends(tmp_path, monkeypatch, crash):
    api = TestClient(create_app(tmp_path / "single.sqlite3", tmp_path / "data"))
    run = paid_run(api, tmp_path, run_id="run_single_attempt")
    submitter = api.app.state.remote_task_submitter

    class SingleAttemptTransport:
        provider_name = "giggle"
        supports_idempotency = False
        requires_single_attempt = True
        calls = 0

        def post_paid_task(self, *, request, idempotency_key):
            self.calls += 1
            observed = api.app.state.repository.list_remote_task_bindings(run.id)[0]
            assert observed.state == RemoteTaskState.AMBIGUOUS_CHARGE
            if crash:
                raise SystemExit("synthetic interruption after dispatch")
            return PaidProviderAcceptance(provider_task_id="single-fixture", receipt={"fixture": True})

    transport = SingleAttemptTransport()
    kwargs = {"task_key": "E01-U01", "provider": "giggle", "model": "MiniMax-H3",
              "request": paid_request("单次提交合成测试"), "transport": transport}
    if crash:
        with pytest.raises(SystemExit):
            submitter.submit_paid_task(run.id, **kwargs)
    else:
        assert submitter.submit_paid_task(run.id, **kwargs).state == RemoteTaskState.SUBMITTED
    recovered = submitter.submit_paid_task(run.id, **kwargs)
    assert recovered.state == (RemoteTaskState.AMBIGUOUS_CHARGE if crash else RemoteTaskState.SUBMITTED)
    assert transport.calls == 1


H3_ZERO_POPULATION_SCOPE = (
    "\npopulation_scope: render exactly 0 living entity instances in total; "
    "background population count=0; unbound living entity count=0"
)

PAID_PACKAGE_BODY = {
    "schema_version": "nalu.production-package/v1",
    "resolved_library": [],
    "production_policy": {
        "requested_model": "MiniMax-H3",
        "paid_generation_approved": True,
        "approved_by": "QA 授权人",
    },
}
PAID_PACKAGE_SHA256 = canonical_sha256(PAID_PACKAGE_BODY)


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
        "prompt": prompt + H3_ZERO_POPULATION_SCOPE,
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
        "provider_scope_projection": {
            "schema_version": "nalu.qingshan-provider-scope/v1",
            "status": "LOCKED",
            "visible_character_ids": [],
            "visible_entity_instance_counts": {},
            "exclusive_visible_living_entity_set": True,
            "visible_living_entity_instance_total": 0,
            "background_population_count": 0,
            "unbound_visible_living_entity_count": 0,
            "visible_prop_ids": [],
            "reference_identity_bindings": [],
            "absent_episode_entities": [],
            "provider_reads_episode_global_contract_directly": False,
            "production_package_sha256": PAID_PACKAGE_SHA256,
            "episode_character_catalog_sha256": canonical_sha256([]),
        },
        "episode_scene_role": "OTHER_SCENE",
        "shot_state_delta_contract": {
            "mode": "CHANGE",
            "dimensions": [
                {"dimension": "POSITION", "entry": "门外", "exit": "门内"},
            ],
        },
    }
    request.update(overrides)
    if "provider_scope_projection" not in overrides and isinstance(
        request.get("visible_prop_ids"), list
    ):
        request["provider_scope_projection"] = {
            **request["provider_scope_projection"],
            "visible_prop_ids": list(request["visible_prop_ids"]),
        }
    return request


def paid_run(
    api: TestClient,
    tmp_path: Path,
    *,
    run_id: str,
    approved: bool = True,
    model: str = "MiniMax-H3",
    resolved_library: list[dict] | None = None,
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
        **PAID_PACKAGE_BODY,
        "resolved_library": list(resolved_library or []),
        "production_policy": {
            "requested_model": model,
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
        requested_model=model,
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
        ({"provider_scope_projection": None}, "provider-scope projection"),
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
    request = paid_request("甲" * (10_000 - len(H3_ZERO_POPULATION_SCOPE)))

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


def test_provider_scope_is_model_aware_and_blocks_absent_entities() -> None:
    registry = ModelCompilerRegistry()
    scope = {
        "schema_version": "nalu.qingshan-provider-scope/v1",
        "status": "LOCKED",
        "visible_character_ids": [],
        "visible_entity_instance_counts": {},
        "exclusive_visible_living_entity_set": True,
        "visible_living_entity_instance_total": 0,
        "background_population_count": 0,
        "unbound_visible_living_entity_count": 0,
        "visible_prop_ids": [],
        "reference_identity_bindings": [],
        "absent_episode_entities": [
            {
                "entity_id": "CHAR-CROW",
                "forbidden_provider_terms": ["black crow"],
            }
        ],
        "provider_reads_episode_global_contract_directly": False,
        "production_package_sha256": PAID_PACKAGE_SHA256,
        "episode_character_catalog_sha256": canonical_sha256([]),
    }
    h3 = paid_request(
        "Only the empty room is visible.\nnegative_constraints: no black crow",
        provider_scope_projection=scope,
    )
    assert "absent episode entity appears in provider prompt: CHAR-CROW" in (
        registry.validate_paid_boundary_request("MiniMax-H3", h3)
    )

    seedance = {
        **h3,
        "adapter_id": "nalu.qingshan.seedance2-pro",
        "profile_id": "SEEDANCE_2_STANDARD_GIGGLE",
        "model": "seedance-2.0-pro",
        "provider_model_id": "seedance-2.0-pro",
        "native_resolution_contract": "720p",
        "delivery_resolution_contract": "720p",
    }
    assert registry.validate_paid_boundary_request("seedance-2.0-pro", seedance) == []


def test_provider_scope_enforces_exclusive_identity_and_population() -> None:
    registry = ModelCompilerRegistry()
    scope = {
        "schema_version": "nalu.qingshan-provider-scope/v1",
        "status": "LOCKED",
        "visible_character_ids": ["CHAR-LIN"],
        "visible_entity_instance_counts": {"CHAR-LIN": 1},
        "exclusive_visible_living_entity_set": True,
        "visible_living_entity_instance_total": 1,
        "background_population_count": 0,
        "unbound_visible_living_entity_count": 0,
        "visible_prop_ids": [],
        "reference_identity_bindings": [
            {
                "reference_index": 1,
                "entity_id": "CHAR-LIN",
                "provider_entity_label": "Grandpa Lin",
                "exclusive_identity_owner": True,
            }
        ],
        "absent_episode_entities": [],
        "provider_reads_episode_global_contract_directly": False,
        "production_package_sha256": PAID_PACKAGE_SHA256,
        "episode_character_catalog_sha256": canonical_sha256([]),
    }
    request = paid_request("placeholder", provider_scope_projection=scope)
    request["prompt"] = (
        "@Image1: exclusive identity of Grandpa Lin; exactly one visible instance of "
        "Grandpa Lin.\npopulation_scope: render exactly 1 living entity instances in "
        "total; background population count=0; unbound living entity count=0"
    )
    assert registry.validate_paid_boundary_request("MiniMax-H3", request) == []

    mutations = (
        ("background_population_count", 1, "zero background population"),
        ("unbound_visible_living_entity_count", 1, "zero unbound living entities"),
        (
            "provider_reads_episode_global_contract_directly",
            True,
            "episode-global contract access",
        ),
    )
    for field, value, message in mutations:
        changed = deepcopy(request)
        changed["provider_scope_projection"][field] = value
        assert any(
            message in failure
            for failure in registry.validate_paid_boundary_request("MiniMax-H3", changed)
        )

    changed_reference = deepcopy(request)
    changed_reference["provider_scope_projection"]["reference_identity_bindings"][0][
        "entity_id"
    ] = "CHAR-ABSENT"
    assert "provider-scope reference owner is not a visible character" in (
        registry.validate_paid_boundary_request("MiniMax-H3", changed_reference)
    )


def test_paid_boundary_derives_complete_character_scope_from_approved_package(
    tmp_path: Path,
) -> None:
    api = TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))
    resolved_library = [
        {"kind": "character", "entity_id": "CHAR-LIN", "stable_name": "林叔"},
        {"kind": "character", "entity_id": "CHAR-MEI", "stable_name": "梅姨"},
        {"kind": "prop", "entity_id": "PROP-CASE", "stable_name": "旧皮箱"},
    ]
    run = paid_run(
        api,
        tmp_path,
        run_id="run_paid_package_scope_authority",
        resolved_library=resolved_library,
    )
    package = json.loads(Path(run.package_path).read_text(encoding="utf-8"))
    scope = {
        "schema_version": "nalu.qingshan-provider-scope/v1",
        "status": "LOCKED",
        "visible_character_ids": ["CHAR-LIN"],
        "visible_entity_instance_counts": {"CHAR-LIN": 1},
        "exclusive_visible_living_entity_set": True,
        "visible_living_entity_instance_total": 1,
        "background_population_count": 0,
        "unbound_visible_living_entity_count": 0,
        "visible_prop_ids": [],
        "reference_identity_bindings": [
            {
                "reference_index": 1,
                "entity_id": "CHAR-LIN",
                "provider_entity_label": "Grandpa Lin",
                "exclusive_identity_owner": True,
            }
        ],
        "absent_episode_entities": [
            {
                "entity_id": "CHAR-MEI",
                "forbidden_provider_terms": ["Grandma Mei"],
            }
        ],
        "provider_reads_episode_global_contract_directly": False,
        "production_package_sha256": package["package_sha256"],
        "episode_character_catalog_sha256": canonical_sha256(
            ["CHAR-LIN", "CHAR-MEI"]
        ),
    }
    request = paid_request("placeholder", provider_scope_projection=scope)
    request["prompt"] = (
        "@Image1: exclusive identity of Grandpa Lin; exactly one visible instance of "
        "Grandpa Lin.\npopulation_scope: render exactly 1 living entity instances in "
        "total; background population count=0; unbound living entity count=0"
    )
    invalid_cases = (
        (
            lambda changed: changed["provider_scope_projection"].update(
                absent_episode_entities=[]
            ),
            "does not cover the production package character catalog",
        ),
        (
            lambda changed: changed["provider_scope_projection"].update(
                production_package_sha256="0" * 64
            ),
            "not bound to the approved production package",
        ),
        (
            lambda changed: changed["provider_scope_projection"].update(
                episode_character_catalog_sha256="0" * 64
            ),
            "character-catalog binding is invalid",
        ),
        (
            lambda changed: changed["provider_scope_projection"]
            ["absent_episode_entities"].append(
                {"entity_id": "CHAR-LIN", "forbidden_provider_terms": []}
            ),
            "visible and absent character sets overlap",
        ),
    )
    transport = IdempotentFakeTransport()
    for index, (mutate, expected) in enumerate(invalid_cases, start=1):
        changed = deepcopy(request)
        mutate(changed)
        with pytest.raises(ConflictError, match=expected):
            api.app.state.remote_task_submitter.submit_paid_task(
                run.id,
                task_key=f"E01-invalid-{index}",
                provider="giggle",
                model="MiniMax-H3",
                request=changed,
                transport=transport,
            )
    assert transport.calls == 0

    accepted = api.app.state.remote_task_submitter.submit_paid_task(
        run.id,
        task_key="E01-valid",
        provider="giggle",
        model="MiniMax-H3",
        request=request,
        transport=transport,
    )
    assert accepted.state == RemoteTaskState.SUBMITTED
    assert transport.calls == 1


def test_only_submitter_source_invokes_paid_transport() -> None:
    runtime_root = Path("services/runtime_api/nalu_runtime")
    callers = {
        path.name
        for path in runtime_root.glob("*.py")
        if ".post_paid_task(" in path.read_text(encoding="utf-8")
    }
    assert callers == {"remote_submitter.py"}
@pytest.mark.parametrize("case", ["ok", "expired", "wrong_amount", "http_error"])
def test_official_price_observation_binds_confirmation_without_generation(tmp_path, case):
    calls = []
    def serve(request):
        calls.append(request)
        assert request.method == "GET"
        assert str(request.url) == "https://apidocs.giggle.pro/8562698m0"
        assert "x-auth" not in request.headers
        return httpx.Response(503 if case == "http_error" else 200, text=
            '<table><tr><td>seedance-2.0-pro</td><td>$0.26 / sec</td><td>26 Credits / sec</td></tr>'
            '<tr><td>seedance-2.0-fast</td><td>$0.22 / sec</td><td>22 Credits / sec</td></tr></table>')
    api = TestClient(create_app(tmp_path / "prices.sqlite3", tmp_path / "data", pricing_http_transport=httpx.MockTransport(serve)))
    run = paid_run(api, tmp_path, run_id="run_quote_fixture", model="seedance-2.0-pro")
    repository = api.app.state.repository
    request = {"model": "seedance-2.0-pro", "duration_seconds": 6}
    record = {"task_key": "E01-U01", "request": request, "request_sha256": canonical_sha256(request),
              "production_package_sha256": "a" * 64}
    record["preparation_sha256"] = canonical_sha256(record)
    prepared = repository.append_run_event(run.id, "video_task_prepared", payload=record)
    base = f"/v1/production-runs/{run.id}/video-task-preparations/{prepared.id}"
    quoted = api.post(base + "/price-observations")
    assert len(calls) == 1
    if case == "http_error":
        assert quoted.status_code == 409
        assert not any(e.event_type == "video_price_observed" for e in repository.list_run_events(run.id))
        return
    assert quoted.status_code == 200, quoted.text
    price = quoted.json()["payload"]
    assert price["estimated_credits"] == 156
    assert price["provider_charge_cap_guaranteed"] is False
    with repository.db.connect() as db:
        db.execute("UPDATE production_runs SET estimated_budget_credits = 200 WHERE id = ?", (run.id,))
        if case == "expired":
            price.update(observed_at="2000-01-01T00:00:00+00:00", expires_at="2000-01-02T00:00:00+00:00")
            price["quote_sha256"] = canonical_sha256({k: v for k, v in price.items() if k != "quote_sha256"})
            db.execute("UPDATE run_events SET payload_json = ? WHERE id = ?", (json.dumps(price), quoted.json()["id"]))
    approval = api.post(base + "/estimate-approvals", json={
        "preparation_sha256": record["preparation_sha256"], "estimated_credits": 155 if case == "wrong_amount" else 156,
        "confirmed_run_budget_credits": 200, "pricing_quote_id": quoted.json()["id"],
        "approved_by": "QA", "confirmation": "合成测试，确认这一镜头的费用预估"})
    assert approval.status_code == (200 if case == "ok" else 409), approval.text
    if case == "ok":
        assert approval.json()["payload"]["published_price_observed"] is True
        assert approval.json()["payload"]["quote_sha256"] == price["quote_sha256"]
    assert repository.list_remote_task_bindings(run.id) == []
