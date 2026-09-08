# Novel controls over real loopback HTTP

Extended the existing CI real-http-smoke script beyond health/OpenAPI/project
creation: save a one-chapter source selection, pause, GET the identical persisted
state, and resume to ready with zero fetched chapters. Uses a separate uvicorn
process and real HTTP on127.0.0.1:18765, isolated temporary SQLite/data directories.
Source is example.com and is never fetched. This is control-transport evidence,
not another download or generated-script claim.

Ruff and the script passed. Checked port18765 free before launch and no listener
after process teardown. Actual 100-chapter website retrieval is documented in
live-full-catalog-import-2026-09-08.md. Native UI, paid writer and full production
acceptance remain open. No SOP promoted.
