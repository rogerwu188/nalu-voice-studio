"""One explicitly selected live test. Re-entry queries the saved task, never resubmits."""

import hashlib
import importlib.util
import json
import os
from dataclasses import asdict
from pathlib import Path

import httpx
from nalu_runtime.database import Database
from nalu_runtime.generation_campaign import GenerationCampaign
from nalu_runtime.giggle_task_query import GiggleTaskQuery
from nalu_runtime.video_pricing import PRICING_URL, parse_rates

ROOT = Path(__file__).resolve().parents[1]
PROMPT = "暖色木桌上的旧故事书翻开，纸页中立起微缩村庄，镜头轻推，无文字、水印。"
REQUEST = {"prompt": PROMPT, "model": "seedance-2.0-pro", "duration": 5,
           "aspect_ratio": "16:9", "resolution": "720p", "generating_count": 1}
CAMPAIGN = "giggle-live-test-2026-09-20"
INTENT = hashlib.sha256((CAMPAIGN + ":user-selected-storybook-v1").encode()).hexdigest()


def main():
    key = os.environ["GIGGLE_API_KEY"].strip()
    db = Database(Path.home() / "Library/Application Support/NaluLiveTests/campaign.sqlite")
    db.initialize()
    ledger = GenerationCampaign(db)
    authority = (ROOT / "docs/qa/giggle-live-test-authorization-2026-09-20.json").read_bytes()
    ledger.authorize(CAMPAIGN, hashlib.sha256(authority).hexdigest(), 10000)
    saved = ledger.accepted_task(CAMPAIGN, INTENT)
    if saved:
        print(json.dumps(asdict(ledger.refresh(CAMPAIGN, INTENT, GiggleTaskQuery(lambda: key)))))
        return
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
        price = client.get(PRICING_URL)
        price.raise_for_status()
    if parse_rates(price.text)["seedance-2.0-pro"] != 26:
        raise ValueError("published rate changed")
    request_sha = hashlib.sha256(json.dumps(REQUEST, sort_keys=True).encode()).hexdigest()
    ledger.reserve(CAMPAIGN, INTENT, request_sha, "video", 130,
                   hashlib.sha256(price.content).hexdigest())
    spec = importlib.util.spec_from_file_location("giggle_skill", Path.home() /
        ".codex/skills/giggle-seedance2-gen/scripts/generation_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    api = module.SeedanceClient(key)
    api.session.trust_env = False
    ledger.claim_dispatch(CAMPAIGN, INTENT, request_sha, media="video")
    result = api.text_to_video(**REQUEST)
    raw = json.dumps(result, sort_keys=True).encode()
    if key.encode() in raw:
        raise ValueError("unsafe receipt")
    task = result["data"]["task_id"]
    ledger.record_acceptance(CAMPAIGN, INTENT, task, hashlib.sha256(raw).hexdigest())
    print(json.dumps({"submitted": True, "task_id": task, "reserved_credits": 130}))


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 -- never log credentials or raw provider exceptions
        print(json.dumps({"status": "stopped_requires_reconciliation", "automatic_resubmit": False}))
        raise SystemExit(1) from None
