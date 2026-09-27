# Live DeepSeek Validation

Date: 2026-09-27. One generated invoice-discount fixture was sent to the actual
DeepSeek API, not a mock adapter. Only synthetic source was transmitted.

| Measurement | Result |
| --- | --- |
| Requested model | deepseek-v4-pro |
| Provider | DeepSeek |
| Baseline verification | Failed |
| Candidate verification | Passed |
| Outcome | verified_candidate |
| Model calls | 1 |
| Provider input tokens | 868 |
| Provider output tokens | 103 |
| Total provider tokens | 971 |
| Engine elapsed time | 3.154 seconds |
| Estimated tokens | 774, distinct from actual provider usage |
| Selected context estimate | 291 tokens |
| Eligible full-source estimate | 28,915 tokens |
| Original repository | Unchanged, clean Git status |

The model changed the discount multiplier from addition to subtraction. The
configured test failed before the change and passed afterward. Candidate edits
were isolated; no automatic edit to the original repository occurred.

Local raw evidence is under
`build/live-check/20260927T033907Z-41a68b/result/` (report, trace and patch).
Runtime artifacts are intentionally excluded from the source-only archive.
Reproduce with `make live-check` after exporting a valid `AI_API_KEY`.

This is one small integration smoke test, not an independent benchmark or proof
of superiority over other agents. Hosted model output and timing may vary.
The credential was supplied to a hidden runtime prompt, never saved to project
source, .env files or the submission archive. Rotate any key shared in chat.
