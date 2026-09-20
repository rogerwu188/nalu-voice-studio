"""Read-only credential/statement connectivity check; never submits generation.

Only allowlisted metadata is printed. No credentials or raw account rows leave
the process. One request, no redirects, proxies or automatic retries.
"""

import json
import os

import httpx


def main():
    key = os.environ.get("GIGGLE_API_KEY", "").strip()
    if not key or "\n" in key or "\r" in key:
        print(json.dumps({"status": "credential_unavailable", "generation_submitted": False}))
        return 1
    try:
        with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
            response = client.get(
                "https://giggle.pro/api/v1/payment/credit-statements",
                params={"page": 1, "page_size": 1, "project_id": ""},
                headers={"x-auth": key},
            )
        status = response.status_code
        data = response.json() if status == 200 else {}
        valid = (data.get("code") == 200 and isinstance(data.get("data"), dict)
                 and isinstance(data["data"].get("list"), list))
        print(json.dumps({"status": "statement_access_verified" if valid else "statement_access_failed",
                          "http_status": status, "generation_submitted": False,
                          "billing_reconciled": False}))
        return 0 if valid else 1
    except Exception:  # noqa: BLE001 -- raw HTTP/JSON failures may expose account data
        print(json.dumps({"status": "read_failed", "generation_submitted": False,
                          "automatic_retry": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
