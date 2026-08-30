# Family memory library

The family memory library turns an uploaded file into verified story knowledge. A
file is evidence; it does not become an authoritative fact merely because OCR or a
model produced a plausible description.

## Memory card

Each managed photo, scanned handwritten page, document, audio note, or reference
video may have one memory card containing:

- title and plain-language description;
- on-device OCR text and the user's spoken context;
- approximate date and place;
- people and their relationship to the storyteller;
- relevance to the story;
- allowed use: reference only, story development, or visual generation;
- immutable revision history, confirmation state, and confirmation audit.

The card links to the managed asset ID. Project deletion removes the card, revisions,
confirmation records, and the managed bytes. Project/privacy exports include the
card and its history. Raw OCR never causes cloud upload.

## Accessible archive flow

1. The user selects a large, obvious photo/document control.
2. Nalu copies the bytes into local managed storage and uses Apple Vision on the Mac
   to recognize text in an image. The result starts as a draft.
3. Nalu asks one question at a time: who, when, where, what happened, why it matters,
   and how the material may be used.
4. The current card is shown as text and read aloud. The user can interrupt, ask for
   repetition, or correct a field by voice or in the visual editor.
5. Every edit appends a revision and makes an earlier confirmation stale.
6. Confirmation includes the exact reviewed revision and channel. “Confirm archive”
   is a local state-machine action, never an inference made by a Realtime model.
7. Only confirmed cards may be treated as narrative authority by a script planner.

For a documentary project, confirmation and use permission are both required. A
confirmed `reference_only` card can help Nalu ask a better question, but only a
confirmed `story_development` or `visual_generation` card may be cited as narrative
authority. The documentary readiness report exposes this distinction before chapter
planning begins.

Example readback:

> 这张记忆卡的标题是“在杭州的全家福”。时间是 1980 年春天，地点是杭州
> 灵隐寺。相关人物有您的妻子和女儿。内容正确时请说“确认归档”；需要修改
> 可以说“地点不是西湖，是灵隐寺”。

## Knowledge relationships

Confirmed people, places, events, objects, organizations, and dates will be resolved
into a project knowledge graph. A proposed merge such as “这是前面提到的王阿姨
吗？” requires user confirmation. Every relationship retains its source memory card
and revision. Conflicting confirmed claims block automatic script authority and cause
Nalu to ask a clarification question.

The first implementation persists versioned memory cards and structured people,
date, place, and evidence links. General entity resolution and contradiction handling
remain an incomplete SOP-06 item.

## Permissions

Knowledge permission and generation permission are separate:

- `reference_only` may help Nalu ask questions but cannot authorize visual copying.
- `story_development` may inform the script but does not authorize a face or voice.
- `visual_generation` still requires active face/voice consent and child guardian
  approval where applicable.

Revoking an asset's biometric consent prevents subsequent production use even if its
memory card remains useful as private historical context.

## Realtime voice integration

The Realtime model may propose structured corrections through allowlisted tools such
as `update_memory_place` or `add_memory_person`. The local Runtime validates the card
ID, revision, project, permissions, and arguments, appends a revision, then returns a
fresh readback. Realtime cannot call `confirm_memory_card` without a dedicated explicit
confirmation turn bound to the reviewed revision.

## QA

- Handwritten Chinese, printed text, rotated scan, blank image, and poor OCR fixtures.
- Long pause, repetition, interruption, correction, stale confirmation, and backtracking.
- Visual-only, voice-only, and combined review paths.
- Cross-project evidence is rejected.
- Unauthorized visual generation and child biometric use fail closed.
- Export/restore and complete deletion preserve or remove the exact revision graph.
- A script citation resolves to the confirmed memory card revision used.
