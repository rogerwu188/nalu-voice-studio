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
- Native unit coverage checks title extraction, the explicit-choice wording,
  query transport, and rejection of a candidate from another host. This local
  environment has a previously recorded Command Line Tools/SwiftPM incompatibility;
  these native tests require the repository macOS CI to compile and execute them.
- No live Wikisource search was issued for this checkpoint, no model/provider
  request was made, no body was read by the new title-search route, and no
  installed-app QA was performed. Existing HTTP 401 remains unretried.
- This advances only the public title-to-candidate subpath. It does not establish
  successful title discovery for arbitrary books, full source import, writer
  generation, user-approved screenplay, episode video, release, signing, or
  notarization. SOP-04 and whole-product completion remain open.
