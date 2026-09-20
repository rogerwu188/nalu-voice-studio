"""Conservative cross-media campaign reservations; not a provider billing cap.

Reservations are never released automatically, including on failure or refund.
A dispatch claim is consumed before network I/O: a crash requires reconciliation,
not another submission. Callers must verify the price evidence before reservation.
"""

import re

from .database import Database
from .repository import ConflictError


def _sha(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value):
        raise ConflictError("a SHA-256 evidence identity is required")


class GenerationCampaign:
    def __init__(self, db: Database):
        self.db = db

    def authorize(self, campaign_id, authorization_sha256, limit_credits):
        _sha(authorization_sha256)
        if not campaign_id or type(limit_credits) is not int or limit_credits <= 0:
            raise ConflictError("explicit positive campaign allowance required")
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT * FROM generation_campaigns WHERE id=?",
                               (campaign_id,)).fetchone()
            if prior:
                if (prior["authorization_sha256"] != authorization_sha256
                        or prior["limit_credits"] != limit_credits):
                    raise ConflictError("campaign authorization cannot be replaced")
                return
            db.execute("INSERT INTO generation_campaigns VALUES (?,?,?)",
                       (campaign_id, authorization_sha256, limit_credits))

    def reserve(self, campaign_id, intent_id, request_sha256, media, credits, price_sha256):
        _sha(intent_id)
        _sha(request_sha256)
        _sha(price_sha256)
        if media not in {"audio", "image", "video"} or type(credits) is not int or credits <= 0:
            raise ConflictError("positive bounded media cost required")
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            campaign = db.execute("SELECT * FROM generation_campaigns WHERE id=?",
                                  (campaign_id,)).fetchone()
            if not campaign:
                raise ConflictError("campaign authorization missing")
            prior = db.execute(
                "SELECT * FROM generation_campaign_intents WHERE id=? OR "
                "(campaign_id=? AND request_sha256=?)",
                (intent_id, campaign_id, request_sha256)).fetchone()
            expected = (intent_id, campaign_id, request_sha256, media, credits, price_sha256)
            if prior:
                actual = tuple(prior[key] for key in (
                    "id", "campaign_id", "request_sha256", "media", "reserved_credits",
                    "price_evidence_sha256"))
                if actual != expected:
                    raise ConflictError("existing request or intent requires reconciliation")
                return
            total = db.execute(
                "SELECT COALESCE(SUM(reserved_credits),0) FROM generation_campaign_intents "
                "WHERE campaign_id=?", (campaign_id,)).fetchone()[0]
            if total + credits > campaign["limit_credits"]:
                raise ConflictError("aggregate audio/image/video campaign allowance exceeded")
            db.execute("INSERT INTO generation_campaign_intents VALUES (?,?,?,?,?,?,0)", expected)

    def claim_dispatch(self, campaign_id, intent_id, request_sha256):
        """Exactly one caller may proceed to network submission after this returns."""
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE generation_campaign_intents SET dispatched=1 "
                "WHERE campaign_id=? AND id=? AND request_sha256=? AND dispatched=0",
                (campaign_id, intent_id, request_sha256)).rowcount
            if changed != 1:
                raise ConflictError("unreserved or previously dispatched request; reconcile first")
