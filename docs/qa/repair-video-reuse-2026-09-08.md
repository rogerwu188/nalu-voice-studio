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
