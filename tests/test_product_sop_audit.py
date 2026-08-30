from pathlib import Path

from scripts.audit_product_sop import audit_sop


def section(number: int, state: str, body: str = "") -> str:
    return (
        f"## SOP-{number:02d} · Test — {state}\n\n"
        "Acceptance:\n\n- criterion\n\n"
        f"{body}\n"
    )


def test_repository_product_sop_is_internally_consistent() -> None:
    result = audit_sop(Path("docs/PRODUCT_SOP.md").read_text(encoding="utf-8"))
    assert result["status"] == "PASS", result["failures"]
    assert result["project_complete"] is False
    assert result["counts"]["PASS"] == 2


def test_pass_with_remaining_work_is_rejected() -> None:
    text = "".join(
        section(
            number,
            "PASS",
            "Evidence:\n- Commit `abc`; GitHub CI passed.\n"
            + ("Still required before `PASS`: human QA.\n" if number == 5 else ""),
        )
        for number in range(14)
    )
    result = audit_sop(text)
    assert result["status"] == "FAIL"
    assert "SOP-05 PASS still declares required work" in result["failures"]


def test_missing_duplicate_and_unsupported_states_are_rejected() -> None:
    text = "".join(section(number, "TODO") for number in range(13))
    text += section(12, "DONE")
    result = audit_sop(text)
    assert result["status"] == "FAIL"
    assert any("duplicate SOP sections" in failure for failure in result["failures"])
    assert any("missing SOP sections" in failure for failure in result["failures"])
    assert any("invalid state" in failure for failure in result["failures"])
