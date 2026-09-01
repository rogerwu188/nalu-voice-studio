# Release metrics and next-episode learning

Nalu treats publication verification and audience metrics as read-only external
evidence. They cannot publish, replace media, start production or silently modify an
approved script.

## Trust boundary

- The default `PublicationLearningVerifier` is disabled and always fails closed.
- An authorized platform integration must be injected explicitly. It may perform only
  read-only identity and metrics lookups; Nalu exposes no publication transport here.
- Every reconciliation and metrics window requires a separate plain-language
  confirmation and a stable 16–200 character idempotency key.
- The verified platform, remote publication ID, channel, published state and immutable
  local release-manifest digest must all match. Child projects additionally require
  guardian approval.
- Reusing an idempotency key for a different request is rejected before another provider
  lookup. A different remote ID cannot replace an existing identity.

## Local persistence

SQLite migration 24 stores three immutable layers:

1. one verified publication identity per production run and platform;
2. digest-bound, time-windowed metrics snapshots;
3. monotonically versioned director strategies bound to one metrics snapshot and one
   later editable episode.

The metrics snapshot retains the exact verification-evidence digest. The strategy uses
deterministic, explainable thresholds and records its observations, directives and
immutable constraints. It never edits the target episode. Applying a recommendation
still requires a new script revision and the normal user/guardian approval flow.

Project export v20 preserves the minimal completed production-source metadata needed by
these records, both publication identities, metric snapshots and the complete strategy
revision history. Import validates every inner digest and project/run/episode reference
before one atomic transaction. It rejects unknown tables, cross-project records,
non-contiguous strategy histories and a recomputed outer backup containing changed
learning data. A production package path belongs to the old machine, so import never
trusts or reuses it: the restored completed source row receives an inert path beneath the
new local data root. Versions v1 through v19 remain importable without learning tables.

## Native macOS presentation

The macOS application reads the versioned strategies and their digest-bound metric
snapshots from the local Runtime. It rejects the entire presentation if the project,
snapshot identity or digest does not match, or if either record says that a publish,
production or external-write action occurred. The latest verified revision appears as a
large-text, read-only card with the platform, metric window, views, completion rate,
plain-language observations and up to three next-episode directives. The card adapts its
metric layout for larger text and can read the complete summary and safety boundary
aloud.

There is deliberately no professional metrics form, apply button, publish control or
production trigger in this experience. An older adult or child does not need to copy
platform numbers. An authorized integration creates the immutable evidence elsewhere;
Nalu only explains it here. Even after a recommendation appears, applying it still means
creating a new script revision and completing the existing user or guardian approval
flow.

## Isolated native-window QA fixture

The repository includes a local-only fixture generator for the large-text, readback and
VoiceOver review. It creates a brand-new SQLite database with one two-episode project,
one immutable metrics snapshot and one next-episode strategy:

```bash
qa_root="$(mktemp -d)"
uv run python scripts/create-native-publication-learning-fixture.py --root "$qa_root"
```

Quit every other Nalu instance first, then launch the release-candidate executable with
the two explicit QA variables printed by the generator:

```bash
NALU_ENABLE_LOCAL_QA=1 \
NALU_LOCAL_QA_APPLICATION_SUPPORT="$qa_root" \
  "/path/to/Nalu Voice Studio.app/Contents/MacOS/NaluVoiceStudio"
```

The native app accepts this override only when the flag is exactly `1`, the directory
already exists, and its symlink-resolved path is a child of the operating system's
temporary directory. An invalid path fails closed instead of falling back to the user's
real Application Support database. If a Runtime is already listening on Nalu's loopback
port, QA also fails closed instead of attaching to possibly unrelated data. Fixture
creation refuses a non-empty directory and performs no provider lookup, paid call,
production or publication. It is test data, not real-platform evidence.

## Explicit non-claims

Offline fixtures prove the contract, restart persistence, mismatch rejection,
idempotency and strategy versioning. They are not evidence that a real platform account
was queried or that a video was published. SOP-10 remains incomplete until an explicitly
authorized test-channel publication and real state/metrics reconciliation are recorded.
