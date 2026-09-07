# Native character-card conversational handoff

IN_PROGRESS: native source connected, compiled UI acceptance pending.

After shot approval the native panel prepares exact-source character cards and
hands their IDs to the existing project-library voice intake. It reloads the
current project's actual entities, checks membership and reads one unconfirmed
character at a time through existing local speech playback. Explicit confirmation
uses the existing revision-bound library endpoint, then advances the queue.
Negative confirmation retains drafts. Project selection clears the queue; an old
project's response cannot replace the newly selected project's library.

The existing large native controls remain; a “核对本集人物” recovery action is
available on approved plans. No professional form or new voice engine is added.
Impeccable's hardening guidance shaped preservation/error behavior. Model keys
are not requested and character preparation does not invoke a model or video API.

Evidence:

- 22 planning/project-library backend tests passed in 19.97s.
- Native tests added for exact approved source route, no writer credential,
  unapproved-plan refusal and preservation after character-preparation failure.
  These new Swift tests have not yet run; the known local toolchain failure is not
  a passing build, and CI/native UI results remain required.
- Whitespace checks passed. No real provider or publication calls made.

Remaining: native CI/manual confirmation and correction QA; voice correction of
existing generated cards without a form; explicit immutable package reconciliation
after new character confirmation; full approved asset/frame/video preparation and
real sequential production/release. No SOP promoted to PASS.
