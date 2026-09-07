# Generated-reference handoff into video dispatch

Status: IN_PROGRESS. A concrete context-validation blocker was fixed; real paid
image/video dispatch and full end-to-end acceptance remain incomplete.

Previously, video dispatch required current project asset IDs to equal the
original production snapshot. Registering references created during that same
production run necessarily added asset IDs, so this valid workflow was refused.
Dispatch now permits those generated outputs only when their registration,
accepted review, design/preparation integrity, kind, project scope and original
production-package binding are verified. Missing original assets, arbitrary new
assets, foreign-run/package outputs and revoked consent remain blocked. Existing
price, package approval, model compiler, frame and durable single-attempt gates
are unchanged. This is not a blanket asset-list relaxation.

Targeted reference lifecycle suite: 14 passed in 13.37s before the final added
preparation-integrity/cross-package assertions. Full final regression: 566 passed
in 141.84s, including those assertions; Ruff and diff checks passed.
Parent resolution commit `7a81e03` passed CI run
[34071848678](https://github.com/rogerwu188/nalu-voice-studio/actions/runs/34071848678).
Native review commit `883c902` CI is still running; this change's CI and native
acceptance remain pending.
The test exercises the real repository and the dispatch context validator after
synthetic reference registration; it does **not** establish a successful paid
dispatch, complete compiler contract or provider billing.

## Current external evidence and next authority work

Read-only verification on 2026-09-07:

- [Official pricing](https://apidocs.giggle.pro/8562698m0) lists SD2 video rates;
  no gpt-image-2-pro image rate was found there.
- [GPT Image Pro endpoint](https://apidocs.giggle.pro/449072504e0) describes task
  submission/results but did not supply the missing image unit price in the
  inspected page. No paid trial was used to discover it.
- The current in-app browser's [developer console](https://giggle.pro/developer)
  displayed a login requirement. This does not imply other browsers are logged
  out. User was asked for 1K/2K image rates or console access, not another key.
- Pinned `vendor/qingshan/tools/giggle_asset_factory.py::generate_image` is the
  reference-asset generation path. `submit_giggle_image_manifest.py::validate_task`
  is the shot/keyframe path with spatial, source-action and identity contracts.
  They are not interchangeable: reference production must use its actual contract,
  not be indefinitely blocked on keyframe-only spatial/action requirements. No
  PASS contracts or permissions have been fabricated to work around either path.

Next: concrete reference-production authority with verified applicable price and
explicit spending approval, separate full keyframe contract compilation, native
accepted-task progress and real sequential video/master/release verification.
