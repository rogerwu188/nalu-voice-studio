# Interactive story source switching

Scope: switching between an imported novel and the user's narrated story.

- Narrated input excludes inactive novel passages from the writer request.
- The project retains a separate SQLite-owned novel bookmark, outside the
  writer-visible conversation state.
- Returning to novel continuation resumes at the prior character offset rather
  than silently restarting the chapter.
- Explicit chapter requests still override the bookmark.
- Regression uses a 60,100-character source, switches to narration, recreates the
  runtime over the same database, and verifies the remaining 100 characters and
  byte-identical request replay.

This is local fixture coverage, not real provider, installed macOS, human or
release acceptance. Full SOP completion remains unproven.

Combined local regression after 839b5f4: 57 tests passed in 13.85s across novel
imports, interactive story, source-to-review journeys, writer service/API,
writer execution/recovery/backup and production authorization. Progress-file
audit reported no failures; its PASS is a metadata check, not product acceptance.
Latest native CI 35528372766 was pending behind live run 35527966749; no restart
or cancellation performed.

Full local backend regression on the 839b5f4 implementation (documentation HEAD
83a54c5): `pytest -q` completed successfully, 889 passed, 2 dependency deprecation
warnings, 541.98 seconds. Session 97205 exited 0; do not restart it as unfinished.
This includes encoded synthetic production fixtures, not real-provider or human
acceptance. CI35528372766 subsequently started runtime, arm64 and x86_64 jobs.
Direct local Swift typecheck session49181 was still running at this checkpoint;
SwiftPM failed before tests with a PackageDescription linker error. Neither is
recorded as native test success.

## Installed episode draft adoption

On the same isolated installed fixture below, entered and sent `采用第一集草稿`,
then `采用第二集草稿`, then repeated `采用第二集草稿`. Native UI displayed both
episodes at script_review/15% and explicitly said no approval or paid production.
Read-only script GETs confirmed each episode has exactly revision1 with its own
distinct fixture content and approved_at=null; second-episode production-runs
GET returned an empty list. This verifies two-episode adoption and replay, not
script approval, production or quality acceptance.

## Installed native source switching

CI35528372766 arm64 artifact10610676702, implementation839b5f4. Downloaded ZIP
SHA256 `4f7850be45e04dde125dac2276e39d0e72b03b2d288171d1eeb5a2a4f362773e`
matches its supplied checksum. Installed under `/tmp/nalu-source-flow-Bg9DVp/app`.
Fixture `/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-native-story-9mlufxnv`,
project `prj_85da080ce9b943ef82d90bf17251749f`, isolated runtime18768.
Launch-only UserDefaults argument `-nalu.ai-service-base-url invalid-local-qa`
deliberately fails endpoint validation before credentials/provider calls.

Using the native text input and Send button:

- `继续下一集`: displayed a writer failure (not search); GET showed revision4,
  web_source, writer_failed, original synthetic novel passage and two drafts.
- `不用小说，听我讲自己的故事`: GET showed revision6, narrated_story,
  writer_failed, no novel_source and the same two retained drafts.

This proves installed input routing/source isolation and failure preservation,
not successful generation, queue concurrency, speech recognition or real user QA.
Both architecture Swift test steps passed in this CI; full CI was still running.
Redundant local typecheck49181 was intentionally terminated after those native
CI results, exit143, and must not be presented as a successful local typecheck.
