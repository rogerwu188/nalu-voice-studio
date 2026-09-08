# Retained production version discovery

Added GET `/v1/episodes/{episode_id}/production-runs`, newest first using the
same timestamp/ID ordering as active-run lookup. Missing episodes return 404;
episodes without runs return an empty list. Reading history never activates an
older run, changes episode state or starts production.

Repair tests now read history after Runtime recreation and verify both child
preflight and parent qa_review remain accessible, another episode returns no
versions, active-run selection remains the child and original files are unchanged.
All three repair cases pass (4.13 seconds); ruff passes and OpenAPI was regenerated.
Synthetic fixture only, not actual repaired video or native history UI acceptance.

Next: connect native version selection as read-only inspection, keeping production
commands bound to the current version; separately implement validated reuse of
eligible prior assets. Do not relax the existing library-only shot-plan inheritance
guard to copy provider tasks or stale approvals across production runs.
