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
  in the current working tree with an explicit `NovelLookupIntent` and routing
  regression cases; that correction still requires full CI and a new installed
  artifact/UI attempt.
- No provider response or billing evidence was captured for the stalled native
  trial, so whether an external provider request left the app is unknown. Do not
  retry this query or any provider request until the external outcome is
  reconciled. No candidate choice, source-body fetch, writing call, script, or
  approval was observed. The isolated app and its owned Runtime were stopped;
  the test-only database is preserved under the system temporary directory.
- The direct title smoke was read-only, but the new native title-search UI route
  did not complete; see the stalled-trial evidence above. No source body was
  read and no screenplay was generated or approved. Existing Hops HTTP 401
  remains unretried.
- This advances only the backend title-to-candidate route; native title lookup
  remains unverified until the corrected route passes CI and the new artifact
  displays candidates for explicit user selection. It does not establish
  successful discovery for arbitrary books, full source import, writer
  generation, user-approved screenplay, episode video, release, Developer ID
  signing, or notarization. SOP-04 and whole-product completion remain open.
