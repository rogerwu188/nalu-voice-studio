# Public novel-title search — narrow checkpoint, 2026-10-17

The title-only novel-writing path now has a read-only, no-credential lookup
against the Chinese Wikisource main-namespace API. Requests are bounded to 2–120
characters and five results, use the fixed `zh.wikisource.org` HTTPS host, pin a
validated public IP, retain TLS verification, reject redirects, require JSON,
and cap the response body. Returned links are constructed on that same host.
The route is project-bound and does not modify the story. Native code validates
the response scope and every candidate host before presenting explicit numbered
choices. Choosing a candidate still starts the existing user-selected import;
search results are not body text, authorization, or an approved script.

When the request does not contain a usable title, or the public catalog returns
no candidates, the app asks for a title/author or a URL. Novel-title lookup does
not fall back to the paid OpenAI web-search request. This narrow fallback only
searches Chinese Wikisource; it does not claim general web discovery.

## Evidence and limitations

- Backend transport/endpoint tests use a mocked HTTPS transport: fixed host,
  ASCII-encoded query, bounded candidate parsing, project binding, and failure
  without story mutation. Focused source/import/story-journey regression: 51 tests passed;
  Ruff passed. OpenAPI contract was regenerated.
- Live, read-only smoke at 2026-10-17 17:26 UTC queried the public API for
  `西遊記`; the first result was the exact work root `西遊記` on the fixed host,
  followed by related works. The API is MediaWiki's read-only `query+search`
  module ([official API documentation](https://www.mediawiki.org/wiki/API:Search/en)).
  This verifies public title discovery only: no result body was fetched in this
  smoke, no user project was changed, and no model/provider call occurred.
- Native unit coverage checks title extraction, the explicit-choice wording,
  query transport, and rejection of a candidate from another host. The first
  full CI (`39053793497`) exposed an overly broad “这本书” match that routed a
  generic download around its existing confirmation gate. The matcher was
  narrowed and a regression test added. Corrected full CI `39054195834` passed
  Runtime, macOS arm64, x86_64, and Universal jobs on `5cfd8f3`; this is CI
  evidence, not installed-app acceptance. Local SwiftPM remains blocked by the
  selected Command Line Tools manifest linker incompatibility; do not alter the
  system toolchain.
- Downloaded Universal artifact `12109366895` from run `39054195834`. Actions
  artifact digest: `sha256:8c4b1b594a5db51262917352f2aa25430812bd0813edf23992bf81900439a531`;
  inner app ZIP SHA-256: `2fca1bcac9f8d6eda8c80539b4d93da80e851ca12b2b3dadc36b020ad4dfb730`.
  `codesign --verify --deep --strict` passed, but the app is ad-hoc signed,
  has no Team ID, and is not notarized.
- Isolated native trial on that exact artifact created a temporary project and
  submitted `帮我找《西游记》小说，改编成短剧`. The UI remained at
  `正在替您上网查找…`; its local story turn remained pending. The bundled
  Runtime log showed the input append but no app-originated
  `/public-novel-search` request or answer write. A separate direct GET to the
  local endpoint returned five public candidates, but that is backend/manual
  evidence, not native UI evidence. Source inspection found the title-only
  catalog branch was guarded by a boolean that also required a URL, leaving the
  title-only case to the generic OpenAI web-research fallback. This was corrected
  with explicit `NovelLookupIntent` routing and four intent regression assertions
  in commit `b12ac4d1d1811a437302f1c4b4c172ea0b8ff184`. Full CI `39057644824`
  passed all four jobs; evidence-doc commit `1ff2600de57e163c45d91adbc1d35b8c0dd21f22`
  also passed all four jobs in CI `39057720814`.
- Downloaded and verified the fixed commit's arm64 artifact `12109804056` from
  run `39057644824` (Actions digest
  `sha256:93f1ac7644a5bb06a32edc86396ebbdb311dd961295b88c4b696107df4ec80b8`).
  Its app ZIP SHA-256 is
  `e17c8b394af309fb981f3625f8052758e07778f15d4b471c32df5ff36c1f6a5e`; archive
  integrity and `codesign --verify --deep --strict` passed. The signature remains
  ad-hoc, with no Team ID and no notarization. This artifact is extracted in an
  isolated temporary directory, not installed in `/Applications`.
- Native UI recheck on 2026-10-17 used that exact extracted artifact
  through Launch Services with `NALU_ENABLE_LOCAL_QA=1`, a fresh temporary
  Application Support directory, and isolated Runtime port `38197`. The
  launch-only AI endpoint was `invalid-local-qa`, so an unexpected generic
  OpenAI fallback could not form a valid provider request. Runtime health
  returned `200`; after creating a QA-only project, the distinct title-only
  request `帮我找《红楼梦》小说，改编成短剧` visibly returned five bounded
  Wikisource candidates, including the exact `紅樓夢` work root. This verifies
  the corrected native title-only candidate-display route on the exact CI
  artifact. No candidate was selected, no source body was fetched, and no
  screenplay/model/provider request or paid action was made. The app was quit;
  the isolated database remains at
  `/var/folders/y4/k84st0yj7fz043tnxkfrjn1w0000gn/T/nalu-title-search-native-qa.i2ZYds/application-support/nalu.sqlite3`.
- QA-scope caveat: an initial launch attempt used the executable directly, then
  CUA opened a second Launch Services instance without the isolation variables.
  That instance remained at the startup screen with Send disabled; no project
  or query was entered. It may have opened the default
  `~/Library/Application Support/Nalu Voice Studio/nalu.sqlite3`; whether that
  startup touched the existing database cannot be established. No default
  support data was inspected or modified afterward. Both artifact-owned Runtime
  processes were stopped, and the successful recheck used only the isolated
  temporary support directory.
- No provider response or billing evidence was captured for the stalled native
  trial, so whether an external provider request left the app is unknown. Do not
  retry this query or any provider request until the external outcome is
  reconciled. No candidate choice, source-body fetch, writing call, script, or
  approval was observed. The isolated app and its owned Runtime were stopped;
  the test-only database is preserved under the system temporary directory.
- The successful native recheck and direct title smoke were read-only catalog
  discovery, not source-body import. No screenplay was generated or approved.
  Existing Hops HTTP 401 remains unretried, and the original stalled trial's
  provider outcome/billing is still unknown; do not retry it pending
  reconciliation.
- This closes only native title-only candidate display for this title on the
  exact extracted CI artifact. It does not establish
  successful discovery for arbitrary books, full source import, writer
  generation, user-approved screenplay, episode video, release, Developer ID
  signing, or notarization. SOP-04 and whole-product completion remain open.
