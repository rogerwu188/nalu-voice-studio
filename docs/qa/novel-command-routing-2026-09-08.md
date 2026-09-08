# Explicit novel download routing

Inspection found two routing inconsistencies: a bare “下载整本书” had no web
execution signal and returned nil; a URL-bearing novel download was classified
as generic confirmation even though the view model subsequently forwarded it to
research/import. The latter was not a total backend block, but an unnecessary
and misleading branch. Explicit novel imports now count as execution signals and
route directly to the existing source discovery/import path.

Protected combinations remain excluded by requestsNovelImport and still use the
separate confirmation path. Added native tests cover bare book download, chapter
import, URL plus writing, web download, and login/purchase/publication/deletion
combinations. They await native CI; no local Swift test execution is claimed.
`git diff --check` passes. Installed voice-to-source-to-script acceptance remains
open. No model calls, downloads, publication or SOP promotion occurred here.
