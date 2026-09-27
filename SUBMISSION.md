# Hackathon 2026 Submission Contract

Mapping of the supplied guideline screenshots, sections 1-14:

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Root Makefile | setup, run, test, clean | make check and clean-environment test |
| Runtime credential | default TUI reads AI_API_KEY | configuration tests |
| No embedded secrets | no hardcoded keys or automatic .env loading | source scanner; separate history review required |
| Text-only input/model | deepseek-v4-pro default, text messages/JSON | adapter payload tests |
| Prescribed model | AI_MODEL, AI_PROVIDER, AI_BASE_URL | exact ID sent, no fallback |
| Standard launch | make run opens TUI | headless Pilot and terminal checks |
| Dependencies | requirements.txt, Python 3.9+, Git, Make | make setup |
| Reproducibility | temperature 0, bounded calls/time/context | reports record model, budgets and Git base |
| Independent evaluation | source-only archive, no machine paths | clean extraction and setup |
| Team tests | make test | fixture, fake-provider and TUI tests |

## Evaluator Workflow

```sh
git clone <TEAM_REPOSITORY>
cd <TEAM_REPOSITORY>
export AI_API_KEY="<PROVIDED_API_KEY>"
make setup
make run
```

Enter the prescribed clean Git repository, verification command and issue text in
the TUI. The target project's own dependencies must be installed in the evaluator
environment. No browser, Docker, local model, image/audio/video input is required.
Linux/macOS with Python 3.9+, Git and Make are the declared host prerequisites.

For a college-hosted prescribed text-only model, configure without source edits:

```sh
export AI_PROVIDER=compatible
export AI_BASE_URL="https://college.example/v1"
export AI_MODEL="<PRESCRIBED_TEXT_MODEL_ID>"
make run
```

The example endpoint is a placeholder. There is no automatic model substitution.
The screenshots do not specify an additional machine-input protocol; this project
accepts issue text in the TUI and also provides a batch CLI.

## Evidence And Limits

Reports record model/provider, Git base, verification command, budgets, outcomes,
provider-reported usage (when available), estimates, time, events and candidate
patch. The original repository is changed only after Apply confirmation.
An already-passing baseline is distinct from a reproduced failing baseline.

Temperature 0 does not guarantee deterministic hosted model output. UTF-8/4
estimates are not exact tokenizer counts or a monetary spending guarantee.
Context reduction compares selected context to eligible indexed source, not to
competitor agents; skipped large files are excluded from that denominator.
Checkouts are not OS sandboxes. Only run trusted repositories/test commands.

## Credential Incident

The older local TUI contained embedded keys. Current source removes them, but
existing Git history and old ZIPs may retain them. Rotate the exposed credentials
with their providers. Do not publish the old history or archives unchanged.
`make package` builds a source-only ZIP without Git history, .env files, run data,
local environments or the generated 114 MiB big.js stress fixture. This does not
revoke previously exposed keys. The scanner is not a full secret audit.

## Final Gate

Extract the archive to a clean environment, run make setup, make test and make run
before submission. Supply a fresh runtime API key for a real model run.
Confirm the organizers' final runtime, exact model and hidden-test protocol.
Synthetic tests do not prove superiority over other agents or universal bug repair.
