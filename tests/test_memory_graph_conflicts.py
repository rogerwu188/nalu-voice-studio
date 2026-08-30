from pathlib import Path

from fastapi.testclient import TestClient
from nalu_runtime.app import create_app


def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "test.sqlite3", tmp_path / "data"))


def create_project(api: TestClient) -> dict:
    return api.post(
        "/v1/projects",
        json={"title": "家庭往事", "audience_mode": "older_adult"},
    ).json()


def create_card(
    api: TestClient,
    project_id: str,
    *,
    filename: str,
    title: str,
    approximate_date: str = "",
    place: str = "",
    people: list[dict] | None = None,
    allowed_use: str = "story_development",
) -> dict:
    asset = api.post(
        f"/v1/projects/{project_id}/asset-imports",
        params={
            "filename": filename,
            "kind": "source_document",
            "name": filename,
        },
        content=f"evidence:{filename}".encode(),
        headers={"Content-Type": "image/jpeg"},
    ).json()
    return api.post(
        f"/v1/projects/{project_id}/memory-cards",
        json={
            "asset_id": asset["id"],
            "title": title,
            "approximate_date": approximate_date,
            "place": place,
            "people": people or [],
            "allowed_use": allowed_use,
        },
    ).json()


def confirm(api: TestClient, card: dict):
    return api.post(
        f"/v1/memory-cards/{card['id']}/confirm",
        json={
            "confirmed_by": "本人",
            "reviewed_revision": card["current_revision"],
            "review_channel": "voice_and_visual",
            "spoken_confirmation": "我确认这张记忆卡并归档",
        },
    )


def test_relationship_conflict_blocks_confirmation_with_both_evidence_links(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    project = create_project(api)
    first = create_card(
        api,
        project["id"],
        filename="family-1.jpg",
        title="全家福",
        people=[{"name": "李小梅", "relationship": "妻子"}],
    )
    assert confirm(api, first).status_code == 200
    candidate = create_card(
        api,
        project["id"],
        filename="family-2.jpg",
        title="另一张全家福",
        people=[{"name": " 李小梅 ", "relationship": "母亲"}],
    )

    report = api.get(f"/v1/memory-cards/{candidate['id']}/conflicts").json()
    assert report["blocking"] is True
    assert report["checked_against_confirmed_cards"] == 1
    assert report["conflicts"][0]["kind"] == "relationship"
    assert report["conflicts"][0]["candidate_memory_id"] == candidate["id"]
    assert report["conflicts"][0]["candidate_revision"] == 1
    assert report["conflicts"][0]["existing_memory_id"] == first["id"]
    assert report["conflicts"][0]["existing_revision"] == 1
    assert report["conflicts"][0]["candidate_asset_id"] == candidate["asset_id"]
    assert report["conflicts"][0]["existing_asset_id"] == first["asset_id"]
    blocked = confirm(api, candidate)
    assert blocked.status_code == 409
    assert "暂时不能归档" in blocked.json()["detail"]
    stored = api.get(f"/v1/projects/{project['id']}/memory-cards").json()
    assert next(card for card in stored if card["id"] == candidate["id"])[
        "confirmation_status"
    ] == "draft"


def test_same_event_with_incompatible_year_is_blocked(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = create_project(api)
    first = create_card(
        api,
        project["id"],
        filename="station-1982.jpg",
        title="第一次离开家乡",
        approximate_date="1982 年秋天",
    )
    assert confirm(api, first).status_code == 200
    candidate = create_card(
        api,
        project["id"],
        filename="station-1985.jpg",
        title="第一次 离开家乡",
        approximate_date="1985 年",
    )

    report = api.get(f"/v1/memory-cards/{candidate['id']}/conflicts").json()
    assert report["blocking"] is True
    assert [item["kind"] for item in report["conflicts"]] == ["event_date"]
    assert confirm(api, candidate).status_code == 409


def test_same_event_with_incompatible_place_is_blocked(tmp_path: Path) -> None:
    api = client(tmp_path)
    project = create_project(api)
    first = create_card(
        api,
        project["id"],
        filename="wedding-a.jpg",
        title="我们的婚礼",
        place="杭州西湖饭店",
    )
    assert confirm(api, first).status_code == 200
    candidate = create_card(
        api,
        project["id"],
        filename="wedding-b.jpg",
        title="我们的婚礼",
        place="北京友谊宾馆",
    )

    report = api.get(f"/v1/memory-cards/{candidate['id']}/conflicts").json()
    assert report["blocking"] is True
    assert [item["kind"] for item in report["conflicts"]] == ["event_place"]


def test_drafts_and_compatible_approximate_dates_do_not_create_false_conflicts(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    project = create_project(api)
    draft = create_card(
        api,
        project["id"],
        filename="unconfirmed.jpg",
        title="第一次离开家乡",
        approximate_date="1999 年",
    )
    assert draft["confirmation_status"] == "draft"
    first = create_card(
        api,
        project["id"],
        filename="confirmed.jpg",
        title="第一次离开家乡",
        approximate_date="1982 年秋天",
        people=[{"name": "王芳", "relationship": "妈妈"}],
    )
    assert confirm(api, first).status_code == 200
    candidate = create_card(
        api,
        project["id"],
        filename="compatible.jpg",
        title="第一次离开家乡",
        approximate_date="大约 1982 年",
        people=[{"name": "王芳", "relationship": "母亲"}],
    )

    report = api.get(f"/v1/memory-cards/{candidate['id']}/conflicts").json()
    assert report["checked_against_confirmed_cards"] == 1
    assert report["blocking"] is False
    assert report["conflicts"] == []
    assert confirm(api, candidate).status_code == 200


def test_reference_only_cards_and_generic_photo_titles_are_not_narrative_conflicts(
    tmp_path: Path,
) -> None:
    api = client(tmp_path)
    project = create_project(api)
    reference = create_card(
        api,
        project["id"],
        filename="reference.jpg",
        title="全家福",
        place="杭州",
        people=[{"name": "赵敏", "relationship": "母亲"}],
        allowed_use="reference_only",
    )
    assert confirm(api, reference).status_code == 200
    first = create_card(
        api,
        project["id"],
        filename="photo-a.jpg",
        title="全家福",
        place="上海",
        people=[{"name": "赵敏", "relationship": "妻子"}],
    )
    report = api.get(f"/v1/memory-cards/{first['id']}/conflicts").json()
    assert report["checked_against_confirmed_cards"] == 0
    assert report["blocking"] is False
    assert confirm(api, first).status_code == 200
    second = create_card(
        api,
        project["id"],
        filename="photo-b.jpg",
        title="全家福",
        place="北京",
        people=[{"name": "钱宁", "relationship": "朋友"}],
    )
    generic_report = api.get(f"/v1/memory-cards/{second['id']}/conflicts").json()
    assert generic_report["blocking"] is False
    reference_candidate = create_card(
        api,
        project["id"],
        filename="reference-candidate.jpg",
        title="另一张照片",
        people=[{"name": "赵敏", "relationship": "母亲"}],
        allowed_use="reference_only",
    )
    reference_report = api.get(
        f"/v1/memory-cards/{reference_candidate['id']}/conflicts"
    ).json()
    assert reference_report["checked_against_confirmed_cards"] == 1
    assert reference_report["blocking"] is False
    assert confirm(api, reference_candidate).status_code == 200
