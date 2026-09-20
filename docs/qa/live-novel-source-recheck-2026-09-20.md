# Real public novel import recheck

Source revision: 2dea341550030bf410930f1a7e736c50abcd183b.
Executed `python scripts/verify_live_novel_import.py --chapters 2` successfully
against https://zh.wikisource.org/wiki/西遊記 using the actual HTTPS reader.

- Directory discovered: 100 chapters.
- Downloaded and persisted: first two chapters only.
- Pause prevents further fetching; reopening the application backend preserves
  chapter one byte-for-byte; resume fetches chapter two.
- Chapter two: 7,321 characters, SHA256
  `e8870e1b49c22d465aaa2f667dc5bfcc84cd961021b262b987ce1d2801447d55`.
- Interactive instruction requesting chapter two produces a writer request
  whose source passage digest matches that saved chapter.
- Isolated database:
  `/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-live-novel-iahnwmsc/nalu.sqlite3`.

No model request was dispatched, no paid call made, and no user project changed.
This is actual network/import/restart/context evidence, not native UI acceptance,
AI adaptation, complete-book import, video generation or overall SOP completion.
The complete backend regression remains live in execution session99274;
do not launch another copy solely because this checkpoint finished.

## Installed application recovery observation

Opened the existing 7721e44 arm64 QA app against this isolated support directory,
port18773, with launch-only writer endpoint `invalid-local-qa` (no paid dispatch).
Native screenshot verified `Isolated live novel QA`, local runtime online, and
the persisted instruction `请改编第二回，先写成一集草稿`. The application correctly
reported that the prior request had no complete result and was not automatically
repeated. This confirms installed conversation recovery from the real-source
database, not a generated script or visible full-chapter reader acceptance.
