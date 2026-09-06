# Giggle SD2 image transport

Status: IN_PROGRESS. No real network/paid call performed.

Implemented the concrete image-to-video HTTP transport from the installed
`giggle-seedance2-gen` skill's `generation_api.py`: fixed
`https://giggle.pro/api/v1/generation/image-to-video`, x-auth, prompt/model/duration,
aspect_ratio/resolution, generating_count and start_frame fields.

It translates a runtime-approved SD2 request using video_transport with mode
image_to_video_start_frame, aspect_ratio and a base64 start_frame. Decoded bytes
must match the approved opening-anchor SHA. The exact Chinese prompt is retained,
duration is integer 4–15, model is seedance-2.0-pro, resolution stays 720p and count
is one. Additional media is rejected rather than silently discarded; omni and H3
remain separate work. Image semantic/format QA is an upstream prerequisite; the
transport hash check alone is not image-quality validation.

The transport declares single-attempt mode, not server-side idempotency support.
No redirects, environment proxies or automatic retries; bounded response and
sanitized acceptance receipt. Missing task identity or failed response is uncertain,
never proof of zero charge. Ten MockTransport/projection tests and Ruff passed.

This transport is not automatically registered or exposed as an unrestricted
endpoint. Remaining integration: verified frame materialization, immutable shot
request/price approval, durable submitter call, task polling/reconciliation,
actual credentialed provider QA and native end-to-end delivery.
