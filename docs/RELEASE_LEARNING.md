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

## Explicit non-claims

Offline fixtures prove the contract, restart persistence, mismatch rejection,
idempotency and strategy versioning. They are not evidence that a real platform account
was queried or that a video was published. SOP-10 remains incomplete until an explicitly
authorized test-channel publication and real state/metrics reconciliation are recorded.
