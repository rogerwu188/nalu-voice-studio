# Two input paths to reviewed episode production

Extended `test_two_episode_writer_drafts_enter_review_with_distinct_bound_receipts`
to run narrated_story and web_source. The web variant imports one synthetic
chapter through public endpoints, fetches it, asserts its text in frozen story
context, saves a clearly synthetic two-episode writer response, reconciles each
episode receipt, explicitly approves episode one and starts local preflight.

Both variants pass (2 tests, 3.91s); Ruff passes. The production package contains
only the approved first script and the project setting, not second-episode text
or raw novel state. Local chapter text remains readable afterwards.

This is integration evidence, not live-model or installed-user acceptance: the
reader and writer content are synthetic, provider_execution_verified is false,
and the run is dry-run. Real writer, native source choice/resume, actual video and
controlled publication remain required. No SOP status is promoted.

Follow-up: both input variants now attempt production before approving either
draft and require409. After explicitly approving episode one and preparing its
run, episode two still returns409. Two cases pass in3.42s; Ruff passes. This
guards episode-specific approval rather than interpreting one approval as a
series-wide production authorization. It remains synthetic integration evidence.
