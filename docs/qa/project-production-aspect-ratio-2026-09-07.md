# Preserve project framing through professional production

Status: IN_PROGRESS. Local compiler/transport guards are not real video acceptance.

The model compiler and its verifier previously hard-coded portrait 9:16 even for
projects with a different explicit ratio. Adapter 1.8.0 now preserves the package's
project ratio; only legacy packages without the field default to 9:16. Zero,
malformed or empty dimensions fail instead of silently selecting a different
format. Planning does not claim that every ratio is supported by every provider:
the concrete transport still checks its own supported ratios and actual pixels.

Video preparation now requires the current project, package, selected transport
ratio and decoded opening-frame ratio to agree. Dispatch rechecks project framing
immediately before HTTP, so a change after durable intent cannot submit an old
format. Existing accepted/uncertain task recovery is still read-only.

The adapter registry is versioned 2026.09.07.1 and resealed; its routes/capabilities
are unchanged. In particular documentary and commercial routes are not falsely
activated. Compilation schema now describes positive project ratios and adapter
1.8.0. Old compiled 1.7.0 contracts must be rebuilt locally and reviewed as needed;
no existing package, saved media or provider task is rewritten by this change.
The first targeted run caught registry/compiler version drift during app startup;
updating the registry version, digest and its binding tests resolved that failure.

Initial targeted compiler/dispatch/registry suite: 110 passed in 39.32s, before
adding the final aspect-change-after-intent case. Both model compilers cover
portrait, landscape, square, legacy omission, invalid ratios and tampering with a
recomputed compilation checksum. Video fixtures now explicitly configure their
square projects rather than accidentally testing square media against portrait
projects. Full final regression: 599 passed in 297.98s, including the final
after-intent case. Ruff, OpenAPI freshness, diff and machine-progress checks
passed. Current-candidate CI remains pending. No external generation occurred.

Preceding source `90441a0` completed CI
[34073133520](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34073133520)
successfully. That verifies the prior native/image handoff and upstream payload
tests, not this newly modified compiler.

Next: complete verified reference price/spending activation and full keyframe
contracts, then real sequential production/master/release and same-candidate
native acceptance. Existing TTS remains the interaction baseline.
