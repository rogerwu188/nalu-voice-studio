# Campaign paid-submission boundary regression

CI35535138645 on 0e76eaa finished with runtime failure:909 tests passed and
`test_only_submitter_source_invokes_paid_transport` failed. All three native
build jobs succeeded; that does not make the entire CI run successful.

Cause: the new isolated generation campaign module directly invoked the paid
video transport outside remote_submitter.py. The source-boundary assertion was
retained unchanged. Campaign video submission now delegates to the centralized
remote submitter, which obtains the budget-claiming campaign adapter and persists
acceptance. The campaign's immutable reservation and one-shot dispatch claim
remain prerequisites, and test-campaign receipts do not become production bindings.

The original failing test now passes; ruff and diff checks pass. Broader campaign
and paid-submission regression is running in session64289; full prior-source
regression remains session99274. Neither unfinished suite proves this revision
fully accepted. No paid request occurred during the repair. Replacement CI and
the same-candidate native/real-provider product acceptance remain required.
