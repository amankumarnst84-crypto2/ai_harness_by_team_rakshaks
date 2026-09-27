# Comparison and Evidence

Research date: 2026-09-27. There is no single universal "best debugger". Model choice, repository, environment, task difficulty, tools, and evaluation rules affect results. This project has not been evaluated head-to-head against frontier coding agents.

## Documented Capability Comparison

| Area | Original harness | AI Harness v2 | Established comparison |
| --- | --- | --- | --- |
| Interaction | CLI | Textual TUI, pipeline/error sidebar, live diff, review before Apply | Aider has terminal pair programming; mini-SWE-agent has interactive workflows |
| Retrieval | Ranked file prefixes | Lexical ranking, Python AST anchors, line excerpts, explicit reads | Aider uses a graph-ranked repository map with symbols and references |
| Token efficiency | Character budget only | Source/feedback bounds, compact memory, output reservation, repeated-action stops, usage accounting | Aider exposes map budgets and prompt caching; mini-SWE-agent exposes configurable agent/model limits |
| Repair loop | Exact replacements and retries | Adds malformed-response recovery, context requests, repeated-action detection | Mature agents expose broader tools and edit capabilities |
| Verification | Baseline and final command | Adds no-op rejection, protected tests/configuration, tracked-file mutation detection, distinct unreproduced-bug status | All results still depend on an adequate evaluator |
| Execution | Local temporary clone | Local temporary clone, process-group cancellation | mini-SWE-agent supports local and container execution environments |
| Model access | External adapter / mock | Groq, DeepSeek, Qwen/campus compatible endpoints, Ollama, custom adapter | Aider and mini-SWE-agent have broader provider integrations |
| Observability | Final JSON/trace | Live events, persistent history, Prometheus metrics, Grafana provisioning | This is a project-specific integration, not a claim competitors lack monitoring |
| Evidence | Small deterministic demo | Automated engine/API/TUI tests, synthetic retrieval microbenchmark | Published benchmark results use different tasks/models/budgets and cannot be compared directly |

Sources: [Aider repository map](https://aider.chat/docs/repomap.html), [Aider configuration options](https://aider.chat/docs/config/options.html), [mini-SWE-agent documentation](https://mini-swe-agent.com/latest/), [SWE-bench leaderboards](https://www.swebench.com/).

The main gaps remain execution isolation, language-aware dependency navigation beyond Python, broader editing tools, environment setup, and real issue evaluations. The current design prioritizes a small auditable core and measurable context costs.

## Measured Against the Original Retrieval

`python3 benchmark.py` generates three repositories with long source files and unrelated archival files. It reproduces the old prefix-selection strategy with its 16,000-character budget and compares the new default 10,000-character source budget plus repository map. The fixture deliberately stresses bugs near the end of long files. Both strategy and default budget differ; this is not an isolated algorithm experiment.

| Fixture | Original context estimate | v2 context estimate | Target present, original / v2 |
| --- | ---: | ---: | --- |
| Invoice discount | 4,082 | 312 | No / Yes |
| Pagination ceiling | 4,068 | 288 | No / Yes |
| Exclusive interval end | 4,067 | 269 | No / Yes |

Aggregate selected-context reduction: approximately 92.9% versus the original strategy on these fixtures. The full eligible source is roughly 44,300 estimated tokens per repository; v2 omits about 99.3% of it. The larger full-source percentage is **not** the comparison to the original harness.

All three predetermined repairs changed the supplied test command from failing to passing. Original repositories remained unchanged, and every patch passed `git apply --check`. These observations test retrieval and plumbing. They do not show that a model can discover the repair, nor establish lower cost per resolved real issue. Estimates are UTF-8 bytes divided by four, not provider invoices. Reproduce fresh evidence with `python3 benchmark.py --output build/microbenchmark.json`; the source archive excludes local run artifacts.

## How to Measure Competitive Debugging

Use one pinned model/version, identical repository revisions and issue sets, equal token/cost and time budgets, identical execution images, and a held-out evaluator. Include bugs from several languages, long/multifile dependencies, and negative cases where no correct fix is possible under the budget. Keep fixtures out of model training/test prompts where possible.

Record resolution rate, regressions, estimated and provider-reported input/output usage, cached tokens where the provider reports them, dollars per resolved issue, median and p95 latency, invalid edit rate, and environment failures. Count all attempts, failed calls, and unresolved issues. Repeat runs and report uncertainty; do not choose only successful trajectories.

`evaluate.py` runs a manifest of identical tasks against specified model endpoints and saves per-task reports plus totals. This is ready for the college's supplied Qwen/DeepSeek model IDs. Its supplied test commands are not a separate hidden evaluator. One actual DeepSeek API smoke test on a generated fixture passed in one call with 971 provider-reported tokens; see LIVE_VALIDATION.md. No head-to-head or real-issue benchmark has been completed. Provider endpoints follow [Groq's documented compatibility](https://console.groq.com/docs/openai), [DeepSeek chat completions](https://api-docs.deepseek.com/api/create-chat-completion/), and [Qwen's compatible API](https://www.alibabacloud.com/help/en/model-studio/first-api-call-to-qwen).

SWE-bench can provide a standardized issue/evaluation workflow, but the local tests here are not SWE-bench. A real competitive claim requires independently reproducible results and the exact model/environment/configuration used. The current adapters, reports, and monitoring provide instrumentation for that future experiment.

## Monitoring Sources

The configuration follows [Grafana provisioning](https://grafana.com/docs/grafana/latest/administration/provisioning/), [Grafana Docker installation](https://grafana.com/docs/grafana/latest/setup-grafana/installation/docker/), and [Prometheus installation](https://prometheus.io/docs/prometheus/latest/installation/). Docker is not installed on this machine, so the Compose stack and rendered Grafana panels remain unverified.
