"""Observed public rates, not a provider-enforced account quote or charge cap."""

import hashlib
import re
import ssl
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html.parser import HTMLParser

import certifi
import httpx

from .repository import ConflictError, Repository
from .video_preparation import digest

PRICING_URL = "https://apidocs.giggle.pro/8562698m0"


class PriceRows(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], [], None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag == "td":
            self.cell = ""

    def handle_data(self, data):
        if self.cell is not None:
            self.cell += data

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.row.append(" ".join(self.cell.split()))
            self.cell = None
        elif tag == "tr":
            self.rows.append(self.row)


def parse_rates(html: str) -> dict[str, int]:
    parser = PriceRows()
    parser.feed(html)
    rates = {}
    for row in parser.rows:
        if not row or row[0] not in {"seedance-2.0-pro", "seedance-2.0-fast"}:
            continue
        if len(row) != 3 or row[0] in rates:
            raise ConflictError("official pricing table is ambiguous")
        credits = re.fullmatch(r"([1-9][0-9]*) Credits / sec", row[2])
        usd = re.fullmatch(r"\$([0-9]+\.[0-9]{2}) / sec", row[1])
        if not credits or not usd or Decimal(usd[1]) * 100 != int(credits[1]):
            raise ConflictError("official pricing units are unrecognized")
        rates[row[0]] = int(credits[1])
    if set(rates) != {"seedance-2.0-pro", "seedance-2.0-fast"}:
        raise ConflictError("official pricing table is incomplete")
    return rates


class VideoPricingService:
    def __init__(self, repository: Repository, transport: httpx.BaseTransport | None = None):
        self.repository, self.transport = repository, transport

    def quote(self, run_id: str, preparation_id: str):
        run = self.repository.get_run(run_id)
        if self.repository.get_project(run.project_id).archived_at:
            raise ConflictError("archived project is read-only")
        event = self.repository.get_run_event(preparation_id)
        if event.run_id != run_id or event.event_type != "video_task_prepared":
            raise ConflictError("shot preparation belongs to another run")
        prepared = event.payload
        if prepared.get("preparation_sha256") != digest({k: v for k, v in prepared.items() if k != "preparation_sha256"}):
            raise ConflictError("shot preparation integrity failed")
        request = prepared["request"]
        if digest(request) != prepared["request_sha256"]:
            raise ConflictError("saved request integrity failed")
        duration = request.get("duration_seconds")
        model = request.get("model")
        if type(duration) is not int or not 4 <= duration <= 15 or model != "seedance-2.0-pro":
            raise ConflictError("pricing requires a supported concrete SD2 image request")
        # Current concrete image transport always generates exactly one clip.
        if type(request.get("generating_count", 1)) is not int or request.get("generating_count", 1) != 1:
            raise ConflictError("quote does not support multiple output clips")
        try:
            with (httpx.Client(transport=self.transport, trust_env=False, follow_redirects=False,
                               timeout=20, verify=ssl.create_default_context(cafile=certifi.where())) as client,
                  client.stream("GET", PRICING_URL) as response):
                if response.status_code != 200:
                    raise ValueError("pricing unavailable")
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 1_000_000:
                        raise ValueError("pricing page exceeds limit")
            rates = parse_rates(raw.decode("utf-8"))
        except Exception:  # noqa: BLE001 -- never expose raw response bodies
            raise ConflictError("official pricing could not be verified; no paid submission performed") from None
        now = datetime.now(UTC)
        record = {"preparation_id": preparation_id, "preparation_sha256": prepared["preparation_sha256"],
                  "request_sha256": prepared["request_sha256"], "model": model,
                  "duration_seconds": duration, "generating_count": 1,
                  "credits_per_second": rates[model], "estimated_credits": rates[model] * duration,
                  "source_url": PRICING_URL, "source_sha256": hashlib.sha256(raw).hexdigest(),
                  "observed_at": now.isoformat(), "expires_at": (now + timedelta(hours=24)).isoformat(),
                  "published_price_observed": True, "provider_charge_cap_guaranteed": False,
                  "generation_performed": False}
        record["quote_sha256"] = digest(record)
        return self.repository.append_run_event(run_id, "video_price_observed",
            message="Published price observed for this exact shot; actual billing is not guaranteed.", payload=record)
