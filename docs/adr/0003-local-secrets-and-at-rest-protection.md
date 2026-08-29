# ADR 0003: Keep provider secrets in Keychain and local content behind OS encryption

- Status: Accepted
- Date: 2026-08-29

## Context

Nalu stores scripts, biometric media and production packages on a user's Mac.
Provider credentials must never enter SQLite, exports, logs, source control or
process arguments. Bundling SQLCipher would add a second database runtime and a
user-managed key-recovery problem before the product has an account system.

## Decision

Provider credentials are generic-password items in the current user's macOS
Keychain with `WhenUnlockedThisDeviceOnly` accessibility. The Runtime process
receives an explicit environment allowlist and no provider credential. A future
paid adapter may request only its named credential after a separate paid-action
authorization; saving a credential never grants that authorization.

SQLite, managed assets, privacy exports and production packages remain normal
local files so backup and recovery are predictable. Nalu restricts their files
to mode `0600` and directories to `0700`. Cryptographic protection at rest is
provided by macOS volume encryption; users handling sensitive material should
enable FileVault. Nalu does not claim application-layer encryption when
FileVault is disabled.

## Consequences

Secrets have OS-backed access control and are absent from portable project data.
Local files are isolated from other non-privileged users, while FileVault covers
offline disk theft. Application-layer encrypted media remains a possible future
option if the threat model or deployment policy requires independent keys.
