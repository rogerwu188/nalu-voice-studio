# Interactive writing → episode review receipt adapter

Status: IN_PROGRESS, not full SOP-04 or production acceptance.

The chat writer stored its raw response digest as a declaration, while the
production line expected a canonical, episode-bound writer receipt. Reusing one
raw response digest for multiple episodes also conflicts with unique receipt
binding. This was a real handoff gap, not a reason to bypass the production gate.

The runtime now constructs a distinct `nalu.interactive_writer_receipt.v1`
envelope per returned episode. It retains the original response, checks its
digest, returned model/task ID, completed finish reason and exact script bytes.
The native adoption flow submits this envelope after creating/reusing the script
revision. Corrections clear previous receipts; local receipt bodies are excluded
from subsequent model context.

This establishes artifact binding only. Provider execution remains false until
the separate provider verification gate passes. It does not approve the script,
charge for video, or publish. Original QingShan receipt validation stays separate.

Automated evidence: two synthetic episodes from one response enter script review
with distinct receipts; repeat receipt submission succeeds idempotently; changed
script bytes or returned task identity are rejected. Existing provider gate tests
remain in the regression suite. Native Swift parsing passed; full CI and actual
provider-to-production QA are still required.

API reference checked: [OpenAI chat completion retrieval](https://developers.openai.com/api/reference/ruby/resources/chat/subresources/completions/methods/retrieve).
Response identity is not itself proof of execution; retrieval requires stored
completions, and compatibility with the user's configured Hops service is not
established by the OpenAI documentation.
