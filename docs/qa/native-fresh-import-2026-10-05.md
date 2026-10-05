# Fresh installed-app Wikisource import and restart QA

Recorded: 2026-10-05 17:39 UTC  
Product code: `3333013f68a27d9418e554bd9ca4de33d7ab63a6`  
Launched candidate: GitHub Actions run `35956403023`, artifact `10790577575`,
run head `b214662e40d16376cd0c1f365181bf533391db7b`. The app/runtime/test source
files are unchanged from the product commit through current repository HEAD
`728d321314a55fcf823af96ab46e5886a09e606b`; intervening commits are documentation-only.

## Candidate identity and boundary

- Outer workflow artifact SHA-256:
  `5e4c0c0328658f5eb2356672b16c7986944f77186256033fdf9846d9c7cba750`.
- Inner app ZIP SHA-256:
  `94050e677af6150be64d18d158ffb37d6ec54591cddaff9b3361a23930ac89ad`.
- `codesign --verify --deep --strict` passed. This artifact is ad-hoc signed,
  has no Team ID, and is not Developer ID signed or notarized.
- Launched via Launch Services with `NALU_ENABLE_LOCAL_QA=1`, isolated
  `NALU_LOCAL_QA_APPLICATION_SUPPORT` under Foundation's temporary directory,
  and QA port `18790`. No user installation or production project was replaced.

## Observed native journey

1. The isolated app and bundled Runtime reached “本地制片厂在线 → 可以创作”.
2. Created a fresh temporary project and submitted
   `导入小说 https://zh.wikisource.org/wiki/西遊記` through the native text UI.
3. The app performed a real public HTTPS catalog/chapter import. Native progress
   reached `30 / 100` saved chapters. “暂停抓取” stopped the import and the UI
   stated saved chapters were retained; it did not restart the download.
4. Expanded the saved-novel reader and opened chapter 2. The app displayed the
   actual saved chapter body, not only the directory title.
5. Quit the app, confirmed its process and port had exited, then relaunched the
   same candidate with the same isolated support directory. The project and
   `30 / 100` paused status restored. Opening chapter 2 again displayed its
   saved body after restart.
6. Quit cleanly again; no `NaluVoiceStudio`/bundled Runtime process remained,
   and port `18790` had no listener. The isolated SQLite file remains in the
   temporary QA directory for inspection; it contains only this test project.

No microphone/speech permission, Keychain access, writer request, model call,
paid generation, episode production, or publication was attempted. The 70
remaining chapters were intentionally not fetched.

## Result scope

PASS for this narrow installed-app checkpoint: fresh URL-based public-source
import, pause, restart recovery, and read-back of saved chapter text. This
closes the previously open fresh-import native UI subgate for the current
product code. It does not show a generated or approved screenplay, name-only
search, full-book import, complete source understanding, episode/video QA,
human/family acceptance, Developer ID signing, notarization, or controlled
publication. SOP-04 and the overall SOP-00–13 goal remain `IN_PROGRESS`.

