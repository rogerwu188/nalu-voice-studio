# Native adopted dialogue preparation

Parent: `c03ccd56857769ecd5a82748bb58222880cb51e3`.

The existing episode recording panel now has a large native action to prepare
confirmed episode audio and captions. No path, SHA, run ID or technical form is
shown. Existing TTS reads the result. This follows the incumbent Operate surface
and Impeccable hardening guidance: wrap notices, disable duplicate submission,
preserve uncertain pending requests and distinguish preparation from completion.

The client requests confirmed captions, checks the content digest and bound
sound/lineage headers, then submits the exact lineage staging request. It does
not download the potentially large whole-episode WAV just to discover identity.
Staging receipts are typed and checked for matching run/lineage, exact managed
relative paths and matching audio/caption hashes. The runtime independently
rechecks actual PCM, approvals, consent and receipt integrity.

Failed staging retains the exact request for explicit retry. Changing sources
requires an explicit current-version refresh; it does not silently alter a
pending retry. Leaving the panel cancels the client wait and suppresses late
speech; this is NOT a claim that a request already received by the runtime was
rolled back. Repeating the same source staging uses the backend replay gate.

New native test covers initial no-op, failed staging, same-version retry without
another export, exact request bodies, foreign context refusal and explicit
refresh. **Native test execution is pending.** Local Swift parse was blocked by
the existing CommandLineTools `SwiftBridging` duplicate module definition; no
claim of compilation or installed native/VoiceOver QA is made.

Backend contracts: 15 dialogue assembly/materializer-binding tests passed in
0.71s; OpenAPI is current. These do not prove the new Swift UI executes. Current
CI must compile/test the new files. No SOP promotion or installed app update.

Next: automatic preparation/selection of the four remaining sound layers,
native mix/production action, installed QA, final content/master approval and
controlled release. Do not fabricate synthetic soundtracks as user production
or turn this staging checkpoint into a claim of end-to-end completion.
