# Runtime Hops writer transport

Status: IN_PROGRESS; new native path is not enabled yet.

The runtime transport posts only to `https://hopsapi.com/v1/chat/completions`,
reads a secret through a trusted callback at invocation time, uses verified TLS
with bundled certifi roots, disables redirects/environment proxy inheritance,
and performs no automatic retries. Request/response sizes and completion-token
limits are bounded. Provider-side storage remains false.

Responses must contain an actual task ID and model string, one stopped choice,
no refusal/tool call, and a valid unapproved writing answer with at most three
unique episodes and nonempty scripts. Duplicate JSON keys are rejected. Returned
model identity is retained as returned, not substituted with the requested alias.
HTTP errors expose only the status code, never response bodies or credentials.

Twelve transport/ledger tests passed using MockTransport: success replays locally,
301/401/429/500 do not redirect or resubmit, and incomplete/missing/duplicate/empty
answers are rejected. Ruff and full-suite results tracked separately.

This is not a live Hops success or a provider task lookup. Existing HTTP 401 is
not retried. Native wiring, trusted request construction, backup handling and
observed-execution binding to production remain required before activation.

Official OpenAI Docs informed the compatible response fields and the decision
not to enable remote storage merely to retrieve a task:
[Create chat completion](https://developers.openai.com/api/reference/ruby/resources/chat/subresources/completions/methods/create),
[Retrieve stored completion](https://developers.openai.com/api/reference/ruby/resources/chat/subresources/completions/methods/retrieve).
Those documents do not establish Hops access or compatibility; mock tests cannot
establish that either.
