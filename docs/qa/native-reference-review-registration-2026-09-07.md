# Native reference review and explicit project permission

Status: IN_PROGRESS. Native code is wired; this candidate still requires Swift CI,
packaged interaction/screenshots and real provider evidence.

The confirmed-shot panel now presents its generated-reference designs one at a
time using the existing native picker, scalable text and image review controls.
It resolves reference task identities from plan ID/design key, checks saved image
bytes and reuses the existing accept/reject endpoint. Accepting the picture alone
does not register it or grant permission.

After acceptance, a separate project-use action presents a plain-language
confirmation; child projects explicitly ask the guardian. The same statement can
be read aloud using the existing TTS path. No professional metadata form or
provider-key field is introduced. Confirmed registration reuses the backend's
durable asset import and causes opening-frame inputs to refresh. Registered state
can be restored from run events; read failures clear actionable stale images.

Impeccable hardening guidance informed the separation of permission from visual
approval, one-image-at-a-time presentation, stale-state handling and preserved
incumbent controls. This is a bounded Operate extension, not visual/voice polish.

Evidence at writing:

- Python reference integration: 14 passed in 6.43s, including the new native-only
  reference-preparation route, validation and existing-task reuse.
- Swift URLProtocol tests cover reference selection → image review → explicit
  registration → restored registration, no provider credentials, no registration
  before acceptance and failed-refresh state. Pure encoding tests exclude payment
  and publication fields from permission requests. Execution awaits this CI.
- Ruff, OpenAPI currency/backward compatibility and diff checks passed.
- Full Python regression: 566 passed in 78.63s, two dependency deprecation warnings.
  No local Swift build claimed: configured local
  CommandLineTools previously failed; compilation is verified through CI.
- Prior 876142a / 34071632998 running, 7a81e03 / 34071848678 pending at observation.
  Neither establishes this new native panel's acceptance.

Outstanding: packaged native usability and pure-voice confirmation QA; production
quote/full QingShan authority, real image submission and task-progress activation;
real episode videos, postproduction QA, masters, controlled release and signed /
notarized same-candidate full SOP acceptance. Empty prepared tasks are not finished
images. Synthetic image/model tests are not real creation evidence.
