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

In Setup, enter a clean target Git repository. The verification command and issue
are optional: leave both blank for repository-only AI review with static checks.
Supply a trusted test command and a specific issue for test-backed debugging.
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

## Repository-Only Mode

In the TUI, set Repository, clear the optional verification command, and click
Run. A blank issue uses a default repository review request. The CLI also accepts
an omitted --issue and --test. Runtime API credentials are still required for AI.

The harness checks eligible Python syntax, JavaScript syntax via installed Node,
and JSON validity without importing or executing project source. It does not
automatically run npm scripts, install dependencies, or invent behavioral tests.
Checks cover at most 200 indexed source files per scan; unsupported languages,
missing runtimes, limits and excluded files are reported explicitly.

Python AST imports and simple JavaScript local import/require statements build a
bounded static dependency graph. Inferred test-import links are included, but
this is not a runtime behavioral graph and does not fully resolve dynamic imports,
aliases or external packages. Related paths inform retrieval; the AI can request
additional files and propose multi-file patches within the existing edit limits.

The Checks tab shows baseline/candidate diagnostics and before/after changed and
affected files. Context shows inferred dependency edges. AI-only concerns are
labeled as unverified findings. No-fix reviews finish as REVIEW COMPLETE rather
than requiring a fabricated edit. No detected syntax change is not proof of
unchanged behavior or correctness.

STATIC CANDIDATE means eligible static checks passed, NOT that runtime tests
passed. Applying it requires an explicit warning confirmation. Unsupported or
incomplete checks yield an unverified candidate without enabling Apply. Existing
test-command runs retain their separate test-backed result labels.

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

## Live Presentation

Run `make present` after `make setup` (Node.js is also required for this optional
JavaScript practice flow). Each invocation creates a new intentionally buggy
49-line invoice.js and fourteen real regression tests under build/presentations, commits a
clean local baseline, and opens the TUI with the repo, command and issue filled
in. Existing projects are never reset. Source creation uses a deterministic
template, not AI generation.

For a real model run, export a fresh AI_API_KEY in the launching terminal, then
click Run. This uses the configured provider/model and consumes API credits.
If no key is exported, interactive `make run` and `make present` now ask for it
using hidden terminal input before opening the TUI. The prompted key is held only
in process memory, not written to files, Keychain or the parent shell environment.
Pressing Enter without a key opens offline-only mode. Noninteractive evaluation
still reads AI_API_KEY without prompting.
Show the failing baseline in Tests, the proposed Code Diff, and the candidate
test result. Apply is an explicit confirmation step. A live model result is not
guaranteed; rehearse with the exact endpoint and model before presenting.

Offline Demo is a separate, explicitly labeled fixed-response simulation with
real edits/tests. It is a fallback pipeline demonstration, not evidence of live
AI capability. A failed baseline is expected for a debugging task. After a
passing candidate, historical failures remain in Tests rather than the current
failures sidebar. New runs clear Activity; saved runs remain in History.

To only create the files for inspection without launching:
`.venv/bin/python tools/presentation.py --prepare-only`

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

Python edit batches are compiled for syntax using the harness Python runtime
before any file in the batch is written. Rejected batches preserve the previous
candidate and return the filename and line number to the model for retry. This
does not validate program semantics or other languages; candidate tests still run
after accepted edits. Projects requiring newer Python syntax need a compatible
harness runtime.

Rejected syntax, unmatched edits and no-op-only responses trigger a bounded
focused retry: the affected file is prioritized with fresh source. A complete
focused file is included when it fits the bounded context and token allowance;
otherwise bounded excerpts are used. The normal 20-edit batch limit also applies
to recovery; four independent fixes are not rejected merely for their count.
Unchanged replacements in a
mixed response are skipped instead of blocking meaningful edits. Truncated
provider responses request a smaller, focused edit. Repeated ineffective actions
still stop; this recovery strategy does not guarantee a model will solve a task.

Common test-discovery filenames (including testinvoice.py and Java/C# test
suffixes) are read-only. These filename guards are conservative heuristics, not
complete test identification for every framework. Quoted JSON credential fields
are redacted, but automatic redaction cannot identify every secret; do not send
sensitive repositories to a hosted provider.

The TUI shows budget used and remaining separately from estimates and provider
usage. Budget accounting uses the larger of cumulative estimated and reported
tokens. Another call requires room for both its input and reserved output, so a
run may stop with tokens remaining. Valid response usage is recorded even when
the response exceeds the budget. These controls are not a guaranteed billing cap.

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
