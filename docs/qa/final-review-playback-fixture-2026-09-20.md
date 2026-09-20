# Final review playback QA preparation — incomplete

## Native attempt and unresolved privacy crash

Downloaded arm64 artifact 10610112029 from CI 35526471420. ZIP SHA-256
`80a5e403ec2f994337a0d58f160cd5df14ef6defbe0b02fc5ed67efcb69a27f7`
matches the artifact checksum. Extracted under `/tmp/nalu-final-review-bs8PLa/app`.
CI arm64 logs explicitly show the playback/no-auto-approval/changed-master test
and FinalReviewViewingGateTests suite passing; this is not installed QA.

Direct executable launch against the isolated root on port 18767 loaded
`合成首帧确认`, episode `海边`, and the QA-review controls. An AX click on the
combined progress/review disclosure unexpectedly invoked the automatic sound
check (GET sealed-master returned 200), not the intended panel expansion.
The application exited 134; owned runtime shut down. macOS logs at
2026-09-20 10:56:58 reported a TCC missing NSSpeechRecognitionUsageDescription
crash, although plutil confirms that key exists in this artifact's Info.plist.
Root cause is unresolved; do not claim missing packaging key or successful QA.

Relaunched the same app with LaunchServices `open -n` and explicit `--env`
QA isolation variables. Next verify startup and use the disclosure's explicitly
named secondary action or screenshot-grounded control, not its combined AX
default action. No privacy permission was granted or bypassed. Final playback,
review submission, and normal-launch speech behavior remain unverified.

Source: `6e7d7f19beb0a7046af6c6b2310cf224b60cf45d`.

The previously recorded `nalu-native-postproduction-qv1poe20` directory
survives but contains no files, including no SQLite database. Directory existence
was not evidence that the old fixture remained usable. Do not launch QA there.

Executed `./.venv/bin/python scripts/create-native-postproduction-fixture.py`.
Session 72514 exited 0 and returned:

- Application support: `/private/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-native-postproduction-97mbu5w_`
- Repair plan SHA-256: `f8abf991d2623cee913a1c692207533a5463a1e1d2423b986c5eb52b43b3a7dd`
- Provider execution verified: false
- Real story or master accepted: false

The script exercises local synthetic rendering and validates QA-review status,
rendered-output integrity and a nonempty repair plan after reopening the database.
It does not prove installed application playback, human review, real-provider
production, signing, notarization or release acceptance. No SOP is promoted.

Next: use the artifact for CI 35526471420, once available, against this isolated
root with NALU_ENABLE_LOCAL_QA=1, NALU_LOCAL_QA_APPLICATION_SUPPORT set to the path
above and a verified free nondefault QA port. Verify unplayed acknowledgement is
rejected, actual playback enables explicit acknowledgement, playing alone does
not approve, and another version cannot inherit acknowledgement. Do not record
synthetic UI automation as real human quality acceptance.
