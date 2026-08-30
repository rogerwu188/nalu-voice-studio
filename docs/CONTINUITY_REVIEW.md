# Continuity extraction and review

Nalu treats continuity extraction as a proposal, never as narrative authority.
This boundary matters especially for autobiography and documentary projects: a
sentence in a generated script is not automatically a true fact about a person.

## Source priority

For an approved script revision, the Runtime uses the first available source:

1. validated `ending_continuity` metadata;
2. explicit `【结尾地点】`, `【结尾时间】`, `【结尾天气】` and `【未解悬念】`
   markers;
3. conservative local extraction from the final scene of legacy unstructured
   Chinese prose.

The third path is deterministic and runs on the Mac. It only examines the
bounded final scene, prefers the last explicit ending heading, and recognizes
clear grammatical statements about time, weather, a named character's
location, clothing, injury, held prop or learned fact. It recognizes a hook
only from an explicit unresolved question or phrases such as “尚未揭晓” and
“仍是个谜”. Ordinary dialogue questions and uncertain phrases such as “也许”
do not create a handoff.

Each semantic result carries the exact approved-script excerpt, extraction rule
and confidence level. The native app can show these excerpts without asking the
creator to fill a professional form. Medium-confidence hooks are called out for
extra attention.

## Confirmation boundary

- The proposal hash binds the exact approved script revision, source, state and
  hooks.
- The app reads every proposed field aloud. Confirmation stays disabled until
  uninterrupted playback completes.
- An edit invalidates the readback and requires a plain-language change summary.
- A separate explicit confirmation creates the immutable continuity snapshot and
  approval audit record.
- Child projects require guardian approval.
- A changed script, changed proposal, duplicate confirmation or ambiguous phrase
  fails closed.

The user may correct or reject any extraction. Only the reviewed snapshot is
inherited by later episodes; evidence text remains advisory and does not become
a family-memory fact.

## Test boundary

Runtime fixtures cover structured metadata, explicit markers, unstructured
legacy prose, final-scene isolation, evidence binding, ambiguous prose,
ordinary dialogue questions, stale proposals, edited proposals, duplicate
confirmation, child guardian protection, export and restore. Swift tests cover
old responses without evidence, new semantic evidence responses and the
readback-before-confirmation gate.
