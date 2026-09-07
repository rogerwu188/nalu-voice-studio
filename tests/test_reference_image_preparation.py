from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.asset_service import AssetService
from nalu_runtime.giggle_task_query import GiggleTaskObservation
from nalu_runtime.image_observation import ImageObservationService
from nalu_runtime.image_preparation import ImagePreparationRequest, ImagePreparationService
from nalu_runtime.image_submission import ImageSubmissionService
from nalu_runtime.reference_assets import validate_registered_reference
from nalu_runtime.repository import ConflictError
from nalu_runtime.video_preparation import digest
from test_image_budget import prepared_image
from test_image_download import png


def reference_plan(tmp_path):
    api, run, old = prepared_image(tmp_path)
    repo = api.app.state.repository
    payload = deepcopy(repo.get_run_event(old["payload"]["approved_plan_event_id"]).payload)
    designs = [{"key": key, "kind": kind, "name": name, "description": description,
                "source_excerpt": "外婆看海。", "existing_asset_id": None}
               for key, kind, name, description in [
                   ("grandma", "character_image", "外婆", "外貌与服装待确认"),
                   ("beach", "scene_reference", "海边", "岸边，光照待确认")]]
    plan = payload["plan"]
    plan["visual_assets"] = designs
    plan["shots"][0].update(visual_asset_keys=["grandma", "beach"], duration_seconds=6)
    plan["shots"].append({**plan["shots"][0], "duration_seconds": 9})
    payload.pop("plan_sha256")
    payload["plan_sha256"] = digest(payload)
    event = repo.append_run_event(run.id, "shot_plan_approved", payload=payload)
    return api, run, event


def test_native_shots_prepare_shared_references_with_budget_and_restart_reuse(tmp_path):
    api, run, plan = reference_plan(tmp_path)
    endpoint = f"/v1/production-runs/{run.id}/shot-plans/{plan.id}/opening-frame-preparations"
    first = api.post(endpoint, json={"shot_index": 0})
    second = api.post(endpoint, json={"shot_index": 1})
    assert first.status_code == second.status_code == 200
    assert first.json()["payload"]["reference_dependency_task_keys"] == ["REF-grandma-design", "REF-beach-design"]
    repo = api.app.state.repository
    refs = [e for e in repo.list_run_events(run.id) if e.payload.get("purpose") == "visual_reference"]
    assert len(refs) == 2
    assert {e.payload["image_task_key"] for e in refs} == {"REF-grandma-design", "REF-beach-design"}
    for event in refs:
        value = event.payload
        assert "approved_shot_index" not in value  # Never selected as an entry frame by the native decoder.
        assert value["project_id"] == run.project_id and value["registered_asset_id"] is None
        assert value["generation_performed"] is False and value["paid_approved"] is False
        assert value["reference_manifest"] == []
        assert value["aspect_ratio"] == ("1:1" if value["visual_asset_key"] == "grandma" else "9:16")
        assert value["design"]["description"] in value["prompt"]
        budget = api.post(f"/v1/production-runs/{run.id}/image-task-preparations/{event.id}/estimate-approvals", json={
            "preparation_sha256": value["preparation_sha256"], "estimated_credits": 10,
            "confirmed_run_budget_credits": 100, "approved_by": "QA", "confirmation": "Synthetic estimate, no real charge"})
        assert budget.status_code == 200, budget.text
        assert budget.json()["payload"]["task_key"] == value["image_task_key"]
    restarted = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    assert restarted.post(endpoint, json={"shot_index": 0}).json()["id"] == first.json()["id"]
    assert len([e for e in repo.list_run_events(run.id) if e.payload.get("purpose") == "visual_reference"]) == 2
    assert not any(e.event_type == "image_submit_intent" for e in repo.list_run_events(run.id))


@pytest.mark.parametrize("registration_case", ["normal", "revoked", "changed_bytes", "changed_confirmation", "commit_interrupted", "child", "rejected"])
def test_reference_request_uses_existing_durable_submission_download_and_review(tmp_path, monkeypatch, registration_case):
    api, run, plan = reference_plan(tmp_path)
    repo = api.app.state.repository
    service = ImagePreparationService(repo, AssetService(repo, tmp_path / "data"))
    prepared = service.prepare_reviewed_reference(run.id, plan.id, "grandma")
    incoming = ImagePreparationRequest.model_validate({k: prepared.payload[k] for k in ImagePreparationRequest.model_fields})
    record, request = service.materialize(run.id, incoming)
    calls = []
    def synthetic_submit(req):
        calls.append(req)
        return httpx.Response(200, json={"code": 200, "data": {"task_id": "reference-fixture"}})
    # Synthetic authority and HTTP receipt only. Production authority is not enabled.
    submission = ImageSubmissionService(repo).submit(run.id, record["image_task_key"], request,
        secret=lambda: "fixture-not-a-key", authorize=lambda *_: None, transport=httpx.MockTransport(synthetic_submit))
    assert submission.event_type == "image_task_submitted"
    observation = ImageObservationService(repo).refresh(run.id, submission.id, SimpleNamespace(query=lambda _: GiggleTaskObservation(
        "reference-fixture", "completed", ("https://example.org/reference.png",), "0" * 64)))
    monkeypatch.setattr("nalu_runtime.image_materialization.download_image", lambda _: png())
    materialized = api.post(f"/v1/production-runs/{run.id}/image-observations/{observation.id}/materialize")
    assert materialized.status_code == 200, materialized.text
    image = materialized.json()
    endpoint = f"/v1/production-runs/{run.id}/image-results/{image['id']}/review"
    review = {"preparation_id": prepared.id, "expected_materialization_sha256": image["payload"]["materialization_sha256"],
              "decision": "accept", "reviewed_by": "QA", "confirmation": "Synthetic reference reviewed, not a real likeness"}
    result = api.post(endpoint, json=review)
    assert result.status_code == 200, result.text
    assert result.json()["payload"]["task_key"] == "REF-grandma-design"
    assert result.json()["payload"]["visual_semantics_verified"] is False
    restarted = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    assert restarted.post(endpoint, json=review).json()["id"] == result.json()["id"]
    assert len(calls) == 1
    assert repo.list_assets(run.project_id, run.episode_id) == []  # Review alone never fabricates registered assets.
    registration = f"/v1/production-runs/{run.id}/reference-reviews/{result.json()['id']}/asset"
    confirmation = {"consent_granted": True, "confirmed_by": "QA", "statement": "Synthetic reference allowed for this project"}
    assert api.post(registration, json=confirmation, headers={"Origin": "https://example.org"}).status_code == 403
    assert api.post(registration, json={**confirmation, "consent_granted": False}).status_code == 422
    if registration_case == "rejected":
        rejected = api.post(endpoint, json={**review, "decision": "reject", "expected_review_event_id": result.json()["id"]})
        assert rejected.status_code == 200
        assert api.post(registration, json=confirmation).status_code == 409
        assert repo.list_assets(run.project_id) == []
        return
    if registration_case == "child":
        with repo.db.connect() as db:
            db.execute("UPDATE projects SET audience_mode='child' WHERE id=?", (run.project_id,))
        assert api.post(registration, json=confirmation).status_code == 409
        confirmation["guardian_approved"] = True
    if registration_case == "commit_interrupted":
        def interrupted(_self, _asset):
            raise RuntimeError("synthetic response interruption after asset commit")
        with monkeypatch.context() as patch:
            patch.setattr(AssetService, "_after_asset_database_commit", interrupted)
            with pytest.raises(RuntimeError, match="synthetic response interruption"):
                api.post(registration, json=confirmation)
        # Existing importer recovers its marker; provenance identifies the committed asset.
        api = TestClient(create_app(tmp_path / "db", tmp_path / "data"))
    registered = api.post(registration, json=confirmation)
    assert registered.status_code == 200, registered.text
    asset = registered.json()
    assert asset["season_id"] is None and asset["episode_id"] is None
    provenance = asset["metadata"]["generation_provenance"]
    assert provenance["identity_qa_verified"] is False and provenance["authentic_historical_photo"] is False
    assert provenance["review_id"] == result.json()["id"]
    validate_registered_reference(repo, repo.get_asset(asset["id"]))
    if registration_case == "revoked":
        with repo.db.connect() as db:
            db.execute("UPDATE assets SET consent_granted=0 WHERE id=?", (asset["id"],))
        with pytest.raises(ConflictError):
            validate_registered_reference(repo, repo.get_asset(asset["id"]))
    if registration_case == "changed_bytes":
        AssetService(repo, tmp_path / "data").managed_path(run.project_id, asset["local_uri"]).write_bytes(b"changed")
    if registration_case == "changed_confirmation":
        confirmation["statement"] = "different scope cannot silently overwrite approval"
    retried = api.post(registration, json=confirmation)
    if registration_case in {"revoked", "changed_bytes", "changed_confirmation"}:
        assert retried.status_code == 409, retried.text
    else:
        assert retried.status_code == 200 and retried.json()["id"] == asset["id"]
    assert len(repo.list_assets(run.project_id)) == 1 and len(calls) == 1


@pytest.mark.parametrize("case", ["unknown", "wrong_task", "stale", "cancelled", "style_changed", "unapproved"])
def test_invalid_reference_requests_never_create_tasks(tmp_path, case):
    api, run, plan = reference_plan(tmp_path)
    repo = api.app.state.repository
    request = {"task_key": "REF-grandma", "visual_asset_key": "grandma", "approved_plan_event_id": plan.id,
               "approved_plan_sha256": plan.payload["plan_sha256"]}
    if case == "unknown":
        request.update(task_key="REF-missing", visual_asset_key="missing")
    if case == "wrong_task":
        request["task_key"] = "E01-U01"
    if case == "stale":
        request["approved_plan_sha256"] = "0" * 64
    if case == "unapproved":
        repo.append_run_event(run.id, "shot_plan_revised", payload={"approved": False})
    with repo.db.connect() as db:
        if case == "cancelled":
            db.execute("UPDATE production_runs SET status='cancelled' WHERE id=?", (run.id,))
        if case == "style_changed":
            db.execute("UPDATE projects SET visual_style='Changed' WHERE id=?", (run.project_id,))
    result = api.post(f"/v1/production-runs/{run.id}/image-task-preparations", json=request)
    assert result.status_code == 409, result.text
    assert not any(e.payload.get("purpose") == "visual_reference" for e in repo.list_run_events(run.id))
