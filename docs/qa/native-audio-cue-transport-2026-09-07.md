# Native sound cues and recording transport — IN_PROGRESS

The native sound-preparation response is no longer discarded. A typed
EpisodeSoundPlan retains its exact event/hash, episode, edited timeline, narration,
sound directions and caption draft. Cue windows must be finite, ordered,
contiguous and cover the returned duration. The review model retains this plan
after successful preparation and clears it when its edit decision changes.

The native recording-attachment transport sends exact sound-plan, cue and asset
identity plus selected source offset. It verifies returned edit-review binding,
actual decoded sample count, audio format, timeline and unapproved final-QA flags;
a different recording cannot be silently adopted. No provider key is sent.

Native fixtures now carry full sound cues. Added tests cover preservation of the
narration, cue-gap rejection, recording attachment and foreign-asset response
rejection. Current native CI has not yet verified these additions. Parent ba811ec
full CI [34096325134](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34096325134)
passed Runtime, ARM, Intel and Universal. Backend synthetic audio workflow passed
again (1 test, 8.70s), scoped Ruff and diff passed.

Remaining: actual visible cue/recording selection and audition, per-take user
confirmation, subtitle alignment and authored audio/master/release integration.
No installed native QA or real narration production is claimed. Local Swift
toolchain remains unavailable; app on disk has not been replaced with this code.
