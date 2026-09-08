# Keep novel import responses on the source task

Native QA exposed an unrelated audience interview question appended after paused
chapter import. The import branch now omits the interview-resume prompt in both
persisted/displayed conversation text and spoken output. Source links remain in
text; ordinary web questions still retain their existing resume behavior. The
explicit combined writing branch remains unchanged and only proceeds when source
import is ready.

Added native formatter assertions for absent/empty resume prompt, preserved
links, no detour and ordinary question resume. Awaiting CI/installed verification;
`git diff --check` passes. Previously exercised artifact a4a0a06 now has full
successful CI34272616095, but that does not verify this later correction.
