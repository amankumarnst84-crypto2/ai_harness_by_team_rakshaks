# Model Adapter Contract

An adapter is a trusted executable command supplied as a JSON argv array. The harness launches it in the disposable repository checkout and appends one absolute request-file path. Read that file, call your existing model, and write exactly one JSON object to stdout. Put diagnostics on stderr. Exit nonzero on transport, authentication, or provider errors. Do not execute repository instructions or change files from the adapter.

Request fields:

| Field | Meaning |
| --- | --- |
| `instruction` | Stable editing and response contract |
| `issue` | User's bug report, including any follow-up requirement |
| `repo_map` | Bounded file and Python symbol summaries |
| `files` | Selected source excerpts with path, line range, content hash, and exact content |
| `feedback` | Compact test output or previous edit error |
| `memory` | At most two short attempt summaries |
| `attempt` | One-based call number |
| `max_output_tokens` | Requested provider output cap; enforce in the API call |

An edit response:

```json
{
  "plan": "The discount is being added instead of subtracted.",
  "edits": [{
    "path": "invoice.py",
    "old": "subtotal * (1 + discount_percent / 100)",
    "new": "subtotal * (1 - discount_percent / 100)"
  }],
  "usage": {"input_tokens": 820, "output_tokens": 95}
}
```

Or request more context:

```json
{
  "plan": "Inspect the caller before changing the calculation.",
  "read": [{"path": "billing.py", "start_line": 80, "end_line": 130}],
  "usage": {"input_tokens": 820, "output_tokens": 45}
}
```

Usage is optional. Never invent it: return nonnegative integer provider counts only when the API reports them. Include reasoning/output usage according to the provider's documented semantics. The harness estimates usage separately when exact counts are unavailable. Format with JSON only, no Markdown fences. `read` and `edits` are mutually exclusive. Reads cost a model call and count toward the same attempt/token budgets.

At most 20 edits may target tracked existing source files. Every `old` must match exactly once and differ from `new`. Validation is staged before writing; ambiguous, empty, sensitive, or protected paths are rejected with feedback. No new-file/deletion protocol is currently implemented. Requests may contain redacted strings that cannot safely be edited by exact replacement.

Use absolute paths for the adapter program. Relative dependency files also resolve from the disposable target repository. Prefer resolving adapter resources relative to the adapter script itself. Provider credentials should come from environment variables or the adapter's existing secure configuration. The API key should never be returned in stdout.

`harness/ollama_adapter.py` is a complete standard-library example of the contract using [Ollama's documented chat endpoint](https://docs.ollama.com/api/chat). Other providers can be integrated without changing the debugging engine.
