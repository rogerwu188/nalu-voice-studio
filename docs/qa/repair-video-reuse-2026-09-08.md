# Repair video reuse — incomplete

GET repair-video-candidates resolves the explicit repair parent and validates
current repair plan/seal, unchanged script, current target draft, exact indexed
shot content and asset snapshot. Original adopted-video validation is reused;
only valid original reviews become available_for_review. Nothing is adopted,
copied, charged or generated. Reordered/edited shots require new video instead
of guessed matching. Original QA failure is not waived: every candidate still
requires fresh review before any reuse.

Three repair integration cases pass14.68s, covering no-source clips, ordinary-run
rejection, invalid current draft, restart-stable candidate identity, and rejection
of incomplete original receipts. The positive clip validator is mocked in this
test: it proves routing/metadata only, NOT real-media reuse. Need real encoded
fixture validation, explicit durable adoption, downstream staging and native
review controls before claiming repaired production. No SOP promotion.

Real encoded synthetic nel8waa9 fixture exposed two integration gaps: unrelated
later audio uploads invalidated all shots, and historical read validation rejected
the explicit repair parent. Compare only exact referenced assets (plus visual
designs), and allow historical read only for the current same-project/season
repair whose immutable package names that parent. Normal preparation never gains
historical access. Four repair tests passed35.63s and ruff passed before additional
negative historical-access coverage.

Actual GET with unmocked decoder/receipt validator now returns shot0 as
available_for_review, video SHA256
f2cc7a1083c17995bc021b6beeedeb0cda4400ba7830276a65c3786eff4c8f50.
Shot1 remains rejected by original-video validation and must be diagnosed, not
waived. This is synthetic encoded media, not a real-provider or quality acceptance.
Explicit adoption/staging/native controls remain missing.

Second-clip rejection traced to continuous-shot tail validation dropping the
explicit repair target during recursive original-source checks. Propagated the
same scoped target through saved-tail reads only; extract/new preparation keeps
the default restrictions and decreasing-shot lineage checks remain intact.
Unmocked nel8waa9 GET now returns both clips available_for_review; second SHA256
4f4f924ffee7eb0865b9964b422bdcc0ed28cb9f478b24df03ed965d904a933e.
Eight repair tests pass23.54s, including exact tail receipt and wrong-run rejection.
Full synthetic render regression started separately; no final repaired master
or adoption acceptance is claimed.

Added native-only POST repair-video-reviews: requires approved repair plan,
current candidate digest and explicit user attestation. Decisions are SQLite
events, exact requests replay identically after Runtime recreation; latest-review
comparison prevents stale accept from replacing a rejection. Existing editing
blocks changed decisions. No provider task, charge or master approval is copied.
Three repair integration cases pass5.78s (positive clip validator still mocked
for decision tests). Actual native adoption and downstream staging remain open.
Previous full-render process handle80195 is missing after interruption, so no
result is claimed; launched a new targeted full-render regression.
