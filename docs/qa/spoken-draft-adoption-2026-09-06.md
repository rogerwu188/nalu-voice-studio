# Spoken draft adoption

Status: IN_PROGRESS — compiled CI and native dictation acceptance pending.

Draft adoption previously required an exact unpunctuated command. A normal
dictation result such as `请采用第一集草稿。` missed the adoption route and was
sent back to the writer. The command now accepts terminal sentence punctuation,
whitespace, polite prefixes, and explicit requests to put an identified episode
draft into review. Chinese episode numbers through ninety-nine and Arabic
numbers 1–999 are supported.

The entire utterance must match. Negations, questions, vague agreement, invalid
numbers, and compound publication requests do not trigger adoption. This only
puts a draft into review; it does not approve a script or start paid production.

XCTest cases cover the accepted variants and rejected intents. Swift parsing and
diff whitespace validation passed locally. Parsing is not compiled test or
native microphone evidence; those remain required before acceptance.

Subsequent compiled evidence: `swift test --package-path apps/macos` passed in
the ARM job of run 34060675399 on c02c8ad (includes the command parser changes).
This establishes compiled regression coverage, not live microphone acceptance.
