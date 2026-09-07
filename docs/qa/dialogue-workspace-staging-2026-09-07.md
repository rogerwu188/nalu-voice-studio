# Adopted dialogue workspace staging

Native POST stages current episode dialogue WAV, captions VTT and source lineage
inside the managed Qingshan exports/provider-results directory. The expected
lineage must still match after revalidating all adopted recordings/captions.
Files use content-version directories, exclusive durable publication, private
permissions and a SQLite receipt. Exact replay returns the same event; changed
or missing committed files fail rather than being overwritten or recreated.
Sealed output and symlinked storage are refused.

Evidence: full synthetic managed-media workflow passed (1 passed, 25 deselected,
59.49s) after fixing a missing Path import in the test. Checks exact staged PCM
and VTT bytes, 0600 WAV, browser Origin rejection, restarted replay without new
event, and damaged staged WAV refusal without overwriting it. Ruff/diff passed;
OpenAPI updated. This is not real family/provider or installed application QA.

Next: bind staged dialogue/caption receipts to the materialization request and
its sound/subtitle contracts; support explicit remaining sound-layer selection,
then final mix/master and controlled release. Native consumption, cancellation,
crash-injection and signed release QA remain open. CI 34107674105 ARM passed;
runtime and Intel were still in progress. No SOP status promotion.
