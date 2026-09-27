# RAKSHAK

A terminal-first, text-only AI debugging harness. It proposes source edits, runs
baseline/candidate tests, shows diffs and failures, and lets you apply a passing
patch to its unchanged Git base. DeepSeek is the default provider.

## Submission Setup

Requires Python 3.9+, Git and Make on Linux/macOS.

```sh
export AI_API_KEY="<PROVIDED_API_KEY>"
make setup
make run
```

In Setup, enter a clean target Git repository and its trusted test command.
Enter the issue in the text area above.
The sidebar tracks Baseline > Retrieve > Model > Modify > Verify > Review, with
errors and token evidence. Code Diff shows automatic candidate modifications.
Tests and Context expose the evidence. Apply asks for confirmation and refuses a
dirty or changed original repository. Demo uses a fixed simulated response with
real local edits/tests and needs no key.

Target dependencies must already be installed. Test commands execute real local
code: use only trusted repositories and commands. Disposable checkouts are not OS
sandboxes; use a container/VM for untrusted code. The model cannot invoke arbitrary
shell commands. Tests/configuration are protected from model edits.

Ctrl+R runs; Ctrl+X or Ctrl+C cancels; Ctrl+P opens the patch; Ctrl+L focuses the
issue; Ctrl+Q quits after cancellation/evidence preservation. History loads runs
by ID. Launch never calls the provider. Missing AI_API_KEY is a visible error on
live runs, not a fallback to another model.

## Configuration

| Variable | Default / purpose |
| --- | --- |
| AI_API_KEY | Runtime hosted API credential |
| AI_PROVIDER | deepseek; also qwen, groq, compatible |
| AI_MODEL | deepseek-v4-pro; exact prescribed text-only model ID |
| AI_BASE_URL | https://api.deepseek.com |
| HARNESS_REPO | Current directory; editable in TUI |
| HARNESS_TEST | Trusted verification command; editable in TUI |
| HARNESS_TOKENS | 12000 estimated tokens |
| HARNESS_ATTEMPTS | 5 calls |
| HARNESS_DATA_DIR | ~/.local/share/rakshak/runs |

No .env file is automatically read. Export process environment variables; never
put a real key in source/docs. For college evaluation, set the exact AI_MODEL,
AI_PROVIDER and AI_BASE_URL. No silent provider/model fallback is performed.

The default follows the current
[DeepSeek models](https://api-docs.deepseek.com/quick_start/pricing/) and
[JSON output](https://api-docs.deepseek.com/guides/json_mode/) documentation.
V4 calls explicitly disable thinking so the output allowance is available for
patch JSON. Temperature is 0; hosted output is not guaranteed deterministic.

## Token Controls

- Ranked lexical retrieval, Python AST symbols and bounded line reads.
- Cached unchanged records, short test feedback and two-step action memory.
- Repeated-action detection, attempt/time/token limits, cancellation.
- Per-call output cap; actual provider usage/cache hits separate from estimates.
- Up to 10,000 tracked paths, 2 MB per indexed file, 32 MB indexed content.
- Generated dependencies, hidden, sensitive and symlink paths excluded.
- Unique replacements in tracked source files up to 200 KB; no arbitrary file
  creation, configuration modification or million-line whole-file repair.

Context reduction uses eligible indexed source, not competitor token use.
Skipped files are shown. UTF-8/4 estimates are not exact tokens or a billing cap.

## Tests / Submission

```sh
make test
make check
make package
```

With a fresh AI_API_KEY exported, `make live-check` runs a small generated fixture
through the exact configured provider/model (up to two paid calls). It sends no
private project source and saves evidence in build/live-check. A fixture success
is an integration smoke test, not a real-world benchmark score.

Live validation on 2026-09-27 passed with DeepSeek: one generated fixture repaired
in one call using 971 provider-reported tokens. See LIVE_VALIDATION.md for the
measured result and its limitations. This is separate from the offline test suite.

Tests use synthetic fixtures/fake providers, not paid model calls. Runs save
report.json, trace.jsonl and candidate.patch under HARNESS_DATA_DIR.
verified_candidate means baseline failed and candidate passed the configured
command. tests_pass_candidate means baseline already passed, not a reproduced fix.
Neither outcome proves correctness against unseen cases.

Archive: dist/rakshak-submission.zip. SUBMISSION.md maps the supplied guidelines
and explains the credential-history incident. Rotate keys embedded in older
versions; do not publish old Git history or ZIPs without separate review.

## Batch / Plain Terminal

```sh
.venv/bin/python -m harness --repo /path/to/clean/repo \
  --issue "Describe the failing behavior" --provider deepseek \
  --model deepseek-v4-pro --test '["python3","-m","pytest","-q"]' \
  --output /path/outside/repo/result
.venv/bin/python -m harness chat --plain
```

Custom adapters: ADAPTER.md. evaluate.py compares model endpoints on the same task
manifest within this harness. It does not evaluate competing agents.

## Optional Grafana

`make metrics` serves aggregate reports on 127.0.0.1:9108 using the same
HARNESS_DATA_DIR as the TUI. No browser or Docker is started by make run.
For the existing Docker stack on a trusted machine:

```sh
export HARNESS_DATA_DIR="$HOME/.local/share/rakshak/runs"
# Export GRAFANA_ADMIN_PASSWORD securely before starting the optional stack.
docker compose -f observability/compose.yaml up -d
```

Grafana: http://localhost:3001. Set the administrator credentials required by the
Compose configuration. Its read-only exporter stays on the Docker network.
The TUI does not claim Grafana is online without probing it. Docker is
optional and never a prerequisite for evaluation. The old browser interface remains
available through python -m harness.server, but make run opens only the terminal.
