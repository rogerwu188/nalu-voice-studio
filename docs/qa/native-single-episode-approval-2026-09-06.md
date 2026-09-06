# Native single-episode script confirmation

Status: bounded native QA; SOP-04 and production remain IN_PROGRESS.

Used the same cf674a9 packaged arm64 app, isolated database and artifact hash
recorded in `native-queue-restoration-2026-09-06.md`. Project:
`prj_5cbd6dab0cec4e7ca756d5f1ddc275ca` (`[QA] 打包编剧凭证双集`).
Both scripts are explicitly synthetic fixtures, not real provider output.

Expanded the native script disclosure. The editor showed episode one's exact
synthetic text and revision 1. Native AXPress first confirmed the synthetic
season plan (initial button-index selection reached that control), then the
script approval control was targeted and its resulting state verified.
No real-user project was approved.

Native state after script confirmation:

- Episode 1 showed revision 1 approved and status `script_approved`, 20%.
- Episode 2 remained `script_review`, 15%, not approved.
- The current-script approve buttons became disabled and revoke appeared.
- Conversation reported preparation readiness, not a generated video.

SQLite independently confirmed episode `ep_7b911d1b2d7041e1b3267be741c5aa2c`
revision 1 approval at `2026-09-06T21:20:44.218592+00:00`; episode
`ep_2059c8fc397b48119046f9964b619c20` revision 1 had no approval timestamp.

This proves bounded native visual approval isolation, not live speech approval,
real writer verification, completed preflight, paid generation or publication.
No production-start control was invoked.
SQLite also confirmed zero production runs for this project after approval.
