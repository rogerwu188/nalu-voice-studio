# ADR 0001: Put a stable runtime boundary in front of Qingshan

- Status: Accepted
- Date: 2026-08-29

## Context

The upstream production line contains mature gates and many history-specific
commands, but no single stable product API. A macOS application must not depend
on filenames or episode-specific scripts.

## Decision

Nalu owns a versioned local Runtime API and immutable production-package
contract. Qingshan is invoked only through an adapter that consumes that
package. Imported historical documentation is informative, not runtime policy.

## Consequences

The product gains a stable interface and testable safety boundary. Adapter work
is required before paid execution can be enabled.
