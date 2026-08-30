from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

VALID_STATES = {"TODO", "IN_PROGRESS", "WAITING_AUTHORIZATION", "PASS", "REGRESSION"}
SECTION_PATTERN = re.compile(
    r"^## SOP-(?P<number>\d{2})\b[^\n]*?\s—\s(?P<state>[A-Z_]+)\s*$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class SOPSection:
    number: int
    state: str
    heading: str
    body: str


def parse_sop(text: str) -> list[SOPSection]:
    matches = list(SECTION_PATTERN.finditer(text))
    sections: list[SOPSection] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append(
            SOPSection(
                number=int(match.group("number")),
                state=match.group("state"),
                heading=match.group(0),
                body=text[match.end() : end],
            )
        )
    return sections


def audit_sop(text: str) -> dict[str, object]:
    sections = parse_sop(text)
    failures: list[str] = []
    expected = set(range(14))
    observed = [section.number for section in sections]
    duplicates = sorted({number for number in observed if observed.count(number) > 1})
    if duplicates:
        failures.append(f"duplicate SOP sections: {duplicates}")
    missing = sorted(expected - set(observed))
    unexpected = sorted(set(observed) - expected)
    if missing:
        failures.append(f"missing SOP sections: {missing}")
    if unexpected:
        failures.append(f"unexpected SOP sections: {unexpected}")

    counts = {state: 0 for state in sorted(VALID_STATES)}
    for section in sections:
        if section.state not in VALID_STATES:
            failures.append(f"SOP-{section.number:02d} has invalid state {section.state}")
            continue
        counts[section.state] += 1
        if "Acceptance" not in section.body:
            failures.append(f"SOP-{section.number:02d} has no acceptance criteria")
        if section.state == "PASS":
            if not re.search(r"(?:Current evidence|Evidence):", section.body):
                failures.append(f"SOP-{section.number:02d} PASS has no evidence section")
            if "Commit" not in section.body or "GitHub CI" not in section.body:
                failures.append(f"SOP-{section.number:02d} PASS lacks commit or CI evidence")
            if "Still required before `PASS`" in section.body:
                failures.append(f"SOP-{section.number:02d} PASS still declares required work")
        elif section.state == "REGRESSION":
            if "Completion audit" not in section.body and "Regression" not in section.body:
                failures.append(f"SOP-{section.number:02d} REGRESSION has no regression evidence")

    project_complete = len(sections) == 14 and all(
        section.state == "PASS" for section in sections
    )
    return {
        "schema_version": "nalu.product-sop-audit/v1",
        "status": "PASS" if not failures else "FAIL",
        "project_complete": project_complete,
        "counts": counts,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Nalu's product completion SOP")
    parser.add_argument("path", nargs="?", default="docs/PRODUCT_SOP.md")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    result = audit_sop(Path(args.path).read_text(encoding="utf-8"))
    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print(
            f"SOP audit {result['status']}; project_complete={result['project_complete']}; "
            f"counts={result['counts']}"
        )
        for failure in result["failures"]:
            print(f"- {failure}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
