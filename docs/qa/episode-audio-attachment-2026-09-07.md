# Actual audio asset → episode cue — IN_PROGRESS

Added native-only `POST /v1/production-runs/{run_id}/audio-takes`. It attaches an
existing managed archive/voice recording to an exact cue of an approved-edit
sound plan. The current edit acceptance and preview receipt are revalidated,
including underlying adopted video bytes. Project/season/episode scope, active
explicit consent record and child guardian requirement must match.

The source is size-bounded, SHA-verified and actually decoded through the existing
postproduction audio reader at 48 kHz stereo. Its selected source range must cover
the cue; no silence padding is permitted. This records a candidate take, not a
listened-to approval, voice clone, speech transcript, caption alignment or master.
The source asset becomes a production dependency so normal deletion cannot remove
it behind the run. Exact retries revalidate current source/consent/approval before
returning the original event; revoked authorization does not permit replay.

Tests: all 26 image-review workflow cases passed in 20.09s. The new path uses a
real encoded WAV containing synthetic tone (not human narration): exact decoded
sample count, insufficient source coverage, wrong hash, browser Origin denial,
restart replay, asset dependency and consent revocation denial are checked.
Ruff, OpenAPI contract and diff checks passed. An initial test exposed that
consent identity belongs to the consent-record table, not hydrated asset fields;
the implementation now reads the authoritative record.

Remaining: native cue/recording selection, take audition/selection, speech-based
subtitle alignment, actual authored five-layer sound, verified final workspace
and master/release QA. No installed native QA or current full CI PASS is claimed.
Parent b6602cb CI 34096641652 was pending; ba811ec CI 34096325134 was running.
No paid provider generation, real family recording or publication occurred.
