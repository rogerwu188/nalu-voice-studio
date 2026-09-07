# Native episode editing entry — IN_PROGRESS

The confirmed-shot-plan surface now contains a collapsible episode editing entry.
It explicitly stages adopted videos, then provides reversible half-second head /
tail trims, per-shot reset and draft save. No keys, hashes, paths or production
fields are entered by the user. Existing Nalu type, large native controls and TTS
notice readback are preserved. Narrow layouts switch the controls to vertical.
The Impeccable skill informed plain-language actions, visible pending/error states
and preservation of local edits. This is an extension, not a new visual identity.

Runtime responses must match run, confirmed plan, source hash, shot order and
submitted ranges, and must not claim generation/master/edit approval. Local cut
changes issue no requests. Same-source reload preserves unsaved changes; failures
retain cuts, and retries carry the same input hash and windows. No automatic POST
occurs on view appearance. Full-source ranges cannot be saved as an edit.

Added serialized native transport/model tests for no automatic calls, local trim,
failed-save preservation, unchanged-source reload, exact retry body, reset, no
provider-key header and rejection of foreign-plan responses. Execution pending CI:
both local build-environment check and focused swift test fail before compiling
application code at PackageDescription.Package.__allocating_init link resolution.
No local native test pass, screenshot, installed-app behavior or visual finish
review is claimed. Existing installed app/data were not replaced or modified.
Ruff (services/tests/scripts) and git diff check passed.

Still required: current macOS CI; installed native accessibility/visual QA and
Impeccable finish review; saved-edit recovery after app restart; actual trimmed
video preview and explicit edit/duration confirmation; caption/audio retiming;
real authored audio, full postproduction/master QA and controlled release.
This is not a completed edit workflow or SOP. Parent c6881bd CI 34091013930 passed;
parent 9802db8 CI 34091496570 remains in progress at this check.
