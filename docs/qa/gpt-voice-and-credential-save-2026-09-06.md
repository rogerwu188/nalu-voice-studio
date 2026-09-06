# GPT voice entry and credential completion fix

User reported entering OpenAI credentials and selecting Done. The screenshot
still showed Not configured. Code inspection confirmed Done only dismissed the
sheet; reopening cleared drafts. Native UI and scoped Keychain lookup both found
no saved OpenAI item. No key was printed, no audio uploaded and no API call made.

Changes:

- Save and Done persists nonblank drafts before closing; unrelated empty SD2/H3
  fields are optional and leave existing keys untouched.
- Keychain writes are read back and compared in memory. Errors remain visible
  in the credential sheet; failed drafts are retained and the sheet stays open.
- GPT Realtime is the default bottom action. Local dictation/read-aloud is an
  explicitly selected alternate mode. Switching to GPT stops local capture/TTS;
  disconnected GPT does not silently enable system speech.
- Suppressed local readback reports incomplete rather than granting review credit.
- The default Realtime time limit is five minutes; cloud/guardian/key consent
  gates remain intact. No automatic paid connection occurs on launch.

Six native regression tests cover routing, suppressed readback, OpenAI-only save,
blank drafts and failed saves. Local Swift syntax parse/diff checks pass; full
Swift build/tests and native layout/save validation await CI and the new binary.
Actual Realtime speech, interruption and cost acceptance remain open. A user
authorized one at-most-five-minute session, but the key must first be saved.
SD2/H3 credential use from Task2-1 is separately authorized; its configuration
location is not yet resolved and no video generation has been submitted.
