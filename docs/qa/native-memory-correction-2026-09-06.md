# Native synthetic memory correction

2026-09-06T17:42Z: macOS Accessibility reads/actions worked again without
permission changes. Resumed the isolated synthetic OCR project, not user data.
Tested Universal app source `75adedc5dc38d3d7de63a4391be419b1b118a504`,
artifact `9993199632`, with previously verified archive/runtime hashes documented
in `memory-correction-restart-2026-09-06.md`.

Native actions: Manage family material → Edit → paste fictional date and place →
Save new revision. The UI returned to the material list and displayed both values.
Read-only SQLite verification after save:

- Date: `1983 年夏天（虚构 QA 更正）`.
- Place: `青湾旧码头（虚构 QA 更正）`.
- Current revision 3, draft, reference_only.
- Original six-line OCR unchanged in revisions 1, 2 and 3.
- Asset consent_granted and guardian_approved both 0.

Automation caveat: AX direct value assignment did not update SwiftUI bindings.
A preliminary space key caused revision 2 containing only a space in place, not
the intended correction. This history was retained, not erased. Normal paste
input then produced the verified revision 3. Chinese IME candidate UI was also
observed during ASCII keystroke automation; paste avoided that. Clipboard items
were preserved/restored without printing their contents. These are automation
input limitations, not evidence that normal user typing failed.

Screenshot: `images/native-memory-corrected-2026-09-06.png` (only the isolated app
window). Owned app PID 74041 was terminated after QA. No microphone, voice
confirmation, biometric authorization, provider or publication was used. This
closes only native text correction/save on the stated candidate; it does not
close real voice or signed-candidate SOP-05 acceptance.
