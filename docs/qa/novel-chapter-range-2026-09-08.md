# Explicit chapter ranges

Source snapshots now recognize 第一章到第二章 / 第1至2章 / 第一回—第二回
and record requested_chapter_end. Source continuation preserves that end bound;
it can complete a partially supplied long chapter but cannot spill into the next
unrequested chapter. Reverse ranges raise a conflict before saving new context.
The existing character budget and unread-chapter stop remain in effect.

Novel and interactive-story suites: 26 passed in6.42s. Tests include Chinese and
Arabic syntax, partial continuation, exhausted range, two chapters and reversed
range. Initial test collection used pytest's reserved request parameter; corrected
to spoken_range before the passing run. No model call or native acceptance is
claimed; this does not implement whole-novel automatic episode planning.
