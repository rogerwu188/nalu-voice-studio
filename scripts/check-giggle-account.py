"""Read-only credential/statement connectivity check; never submits generation.

Only allowlisted metadata is printed. No credentials or raw account rows leave
the process. One request, no redirects, proxies or automatic retries.
"""

import argparse
import json
import os
from decimal import Decimal, InvalidOperation

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", default="")
    args = parser.parse_args()
    key = os.environ.get("GIGGLE_API_KEY", "").strip()
    if not key or "\n" in key or "\r" in key:
        print(json.dumps({"status": "credential_unavailable", "generation_submitted": False}))
        return 1
    try:
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            response = client.get(
                "https://giggle.pro/api/v1/payment/credit-statements",
                params={"page": 1, "page_size": 100, "project_id": args.task_id},
                headers={"x-auth": key},
            )
        status = response.status_code
        data = response.json() if status == 200 else {}
        valid = (data.get("code") == 200 and isinstance(data.get("data"), dict)
                 and isinstance(data["data"].get("list"), list))
        observations = []
        if valid:
            for row in data["data"]["list"]:
                if args.task_id and (not isinstance(row, dict) or row.get("project_id") != args.task_id):
                    continue
                if not isinstance(row, dict) or row.get("event_type") != "Pay":
                    continue
                if row.get("event_description") not in {
                    "SingleGenerateImage", "SingleGenerateAudio", "SingleGenerateVideo"
                }:
                    continue
                try:
                    amount = Decimal(str(row.get("credit")))
                except InvalidOperation:
                    continue
                if not amount.is_finite():
                    continue
                item = {"media_event": row["event_description"], "charged_credits": str(abs(amount))}
                if item not in observations:
                    observations.append(item)
        print(json.dumps({"status": "statement_access_verified" if valid else "statement_access_failed",
                          "http_status": status, "generation_submitted": False,
                          "recent_historical_charges_not_quotes": observations,
                          "billing_reconciled": False}))
        return 0 if valid else 1
    except Exception:  # noqa: BLE001 -- raw HTTP/JSON failures may expose account data
        print(json.dumps({"status": "read_failed", "generation_submitted": False,
                          "automatic_retry": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
