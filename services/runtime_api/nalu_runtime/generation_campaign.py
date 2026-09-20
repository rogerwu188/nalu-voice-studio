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

    def claim_dispatch(self, campaign_id, intent_id, request_sha256, *, media=None):
        """Exactly one caller may proceed to network submission after this returns."""
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE generation_campaign_intents SET dispatched=1 "
                "WHERE campaign_id=? AND id=? AND request_sha256=? AND dispatched=0 "
                "AND (? IS NULL OR media=?)",
                (campaign_id, intent_id, request_sha256, media, media)).rowcount
            if changed != 1:
                raise ConflictError("unreserved or previously dispatched request; reconcile first")

    def image_transport(self, campaign_id, secret, *, transport=None):
        """Bind the real serialized image request to a reserved one-shot claim."""
        from .giggle_image_transport import GiggleImageTransport

        return GiggleImageTransport(
            secret, transport=transport,
            authorize=lambda intent, request: self.claim_dispatch(
                campaign_id, intent, request, media="image"),
        )

    def record_acceptance(self, campaign_id, intent_id, task_id, response_sha256):
        """Persist only safe receipt fields; never infer completion or billing."""
        _sha(response_sha256)
        if not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,240}", task_id):
            raise ConflictError("invalid provider task identity")
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            intent = db.execute(
                "SELECT dispatched FROM generation_campaign_intents WHERE id=? AND campaign_id=?",
                (intent_id, campaign_id)).fetchone()
            if not intent or not intent["dispatched"]:
                raise ConflictError("acceptance requires a dispatched campaign intent")
            prior = db.execute(
                "SELECT * FROM generation_campaign_receipts WHERE intent_id=? OR provider_task_id=?",
                (intent_id, task_id)).fetchone()
            if prior:
                if tuple(prior) != (intent_id, task_id, response_sha256):
                    raise ConflictError("conflicting provider acceptance; reconcile first")
                return
            db.execute("INSERT INTO generation_campaign_receipts VALUES (?,?,?)",
                       (intent_id, task_id, response_sha256))

    def accepted_task(self, campaign_id, intent_id):
        with self.db.connect() as db:
            row = db.execute(
                "SELECT r.* FROM generation_campaign_receipts r JOIN generation_campaign_intents i "
                "ON i.id=r.intent_id WHERE i.campaign_id=? AND i.id=?",
                (campaign_id, intent_id)).fetchone()
            return dict(row) if row else None

    def submit_image(self, campaign_id, secret, request, intent_id, *, transport=None):
        result = self.image_transport(campaign_id, secret, transport=transport).submit(
            request, intent_id=intent_id)
        self.record_acceptance(campaign_id, intent_id, result["provider_task_id"],
                               result["response_sha256"])
        return result

    def submit_video(self, campaign_id, secret, request, intent_id, *, transport=None):
        result = self.video_transport(campaign_id, secret, transport=transport).post_paid_task(
            request=request, idempotency_key=intent_id)
        self.record_acceptance(campaign_id, intent_id, result.provider_task_id,
                               result.receipt["response_sha256"])
        return result

    def video_transport(self, campaign_id, secret, *, transport=None):
        """Use this factory for campaign-funded SD2 requests, not a bare adapter."""
        from .giggle_video_transport import GiggleSeedanceImageTransport

        return GiggleSeedanceImageTransport(
            secret, transport=transport,
            authorize=lambda intent, request: self.claim_dispatch(
                campaign_id, intent, request, media="video"),
        )
