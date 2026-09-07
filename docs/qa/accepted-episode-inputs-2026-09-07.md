# Accepted episode video inputs — IN_PROGRESS

Added a native-only staging endpoint requiring one current adopted video for every
shot in the current approved plan. It revalidates actual immutable video and
preparation lineage, preserves shot order, and emits typed PostproductionShotSource
entries with video/review hashes and provider task identity. Copies are private,
atomically linked and versioned under the managed package workspace's exports /
provider-results / accepted-shots. Existing differing files are rejected.

The service reads one video at a time rather than holding a whole episode's media
in memory. It rejects paths outside managed run storage, symlink components,
duplicate shot identities and overlong episodes. Replay checks files before
returning an existing receipt. Staging does not change run/billing state or
manufacture workspace manifests, audio, captions, creative QA or a master.

33 regressions passed in 15.64s. The two-shot synthetic fixture now adopts both
videos, stages them in order with exact bytes and private permissions, recovers
after restart, rejects missing second adoption and detects corrupted staged files.
Initial test found the existing materializer requires provider-results-relative
paths; staging was aligned with that contract before passing. Ruff/OpenAPI passed.

Still required: connect native staging, verified Qingshan workspace/receipt inputs,
audio layers and subtitles, RUNNING/QA transition, real materializer execution,
semantic QA, sealing and controlled release. This is not completed postproduction.
Current CI required; parent bf5d9a6 CI 34089503454 pending at check.

Follow-up: af11563 CI 34090041530 passed. Staging windows are full unedited sources,
not a render-ready timeline: Qingshan forbids whole-provider-video passthrough.
Explicit editorial-selection-incomplete flags and the remaining sound/caption
work are documented in [sound-plan evidence](episode-sound-plan-2026-09-07.md).
