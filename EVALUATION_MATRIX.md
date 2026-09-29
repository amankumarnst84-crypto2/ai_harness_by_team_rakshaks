# Composite Evaluation Framework for Agentic Repair Harnesses (v1.0)

Adopts SWE-bench F2P/P2P standards, CodeXGLUE AST matching, and AgentBench safety conventions. Extends them with harness-specific metrics for context economics and anti-tamper governance.

> **Document Version:** 1.0.0  
> **Target Framework:** Rakshak Autonomous AI Harness  
> **Benchmark Standards Aligned:** SWE-bench (ICLR 2024) and CodeXGLUE (Microsoft).

---

## 1. Executive Summary: Why Traditional Text Metrics (BLEU) Fail for Coding Harnesses

In natural language processing, **BLEU (Bilingual Evaluation Understudy)** measures n-gram precision against reference translations. However, applying raw BLEU to autonomous software engineering and repair harnesses yields fatal flaws:

| Metric | How it works | Why it fails / succeeds in Code Repair |
| :--- | :--- | :--- |
| **BLEU Score** | Surface-level token overlap (1-to-4 grams) | ❌ **High False Positives & Negatives:** Changing `+` to `-` gives 99.9% BLEU score despite fixing nothing; renaming valid variables drops BLEU to 40% while being 100% functionally correct. |
| **CodeBLEU** | Adds AST match & Dataflow match to n-grams | ⚠️ **Better for code completion**, but still ignores whether the system actually builds, tests pass, or bugs are fixed. |
| **Execution-Based Evaluation (SWE-bench Standard)** | Dynamic containerized test execution (Fail-to-Pass & Pass-to-Pass) | ✅ **Globally Recognized Ground Truth:** Directly verifies whether the defect is remediated without causing regressions. |

For **Rakshak**, which operates as a token-conscious, self-verifying repair harness, the evaluation matrix must evaluate **5 core dimensions**:
1. **Functional Correctness & Resolve Rate** (Dynamic verification)
2. **Context & Token Economics** (Efficiency & retrieval quality)
3. **Safety, Integrity & Anti-Tamper** (Governance & sandbox trust)
4. **Code Quality & Blast Radius** (Semantic precision)
5. **Operational Resilience & Speed** (Execution & error recovery)

---

## 2. The 5-Dimensional Evaluation Matrix (P.E.R.S.T Framework)

```
                       ┌──────────────────────────────────────────────┐
                       │ COMPOSITE HARNESS EVALUATION MATRIX (PERST)  │
                       └──────────────────────┬───────────────────────┘
                                              │
    ┌──────────────────┬──────────────────────┼──────────────────────┬──────────────────┐
    ▼                  ▼                      ▼                      ▼                  ▼
┌──────────────┐ ┌──────────────┐      ┌──────────────┐      ┌──────────────┐    ┌──────────────┐
│  Performance │ │  Economics   │      │ Reliability  │      │    Safety    │    │ Transparency │
│ & Correctness│ │   & Tokens   │      │  & Quality   │      │ & Integrity  │    │& Observabilit│
└──────────────┘ └──────────────┘      └──────────────┘      └──────────────┘    └──────────────┘
```

---

### Strict Evidence Taxonomy
To prevent overclaiming, every metric reported below is strictly tagged with an Evidence Tier.

| Tier | Meaning | Validation Threshold |
| :--- | :--- | :--- |
| **T0 — Untested** | No runs | Metric defined, but no empirical data collected. |
| **T1 — Pilot** | Smoke test | $N < 10$, synthetic bugs or predetermined fixtures. Not statistically meaningful. |
| **T2 — Internal** | Small-scale real | $N \ge 30$, real bugs evaluated on live LLM APIs. |
| **T3 — Benchmarked** | Standard scale | $N \ge 100$ on established datasets (e.g., SWE-bench Lite). |
| **T4 — Leaderboard** | Peer-reviewed | Published, third-party reproducible leaderboard result. |

---

### Dimension 1: Functional Correctness & Repair Efficacy (SWE-bench Aligned)

Evaluates whether the agentic loop actually resolves the issue without introducing regressions.

| Metric ID | Metric Name | Mathematical Definition / Formula | Industry Baseline | Tier | Rakshak Actual |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M1.1** | **Resolve Rate ($RR$)** | $$RR = \frac{N_{\text{resolved}}}{N_{\text{total}}} \times 100$$ | 38%–49% [SWE-bench, 2024]<br>1.7% [SWE-bench Lite GPT-4, 2023] | **[T1]** | Pilot: 3/3 fixtures passed (N=3). See §4 for scale-up protocol. |
| **M1.2** | **Fail-to-Pass Rate ($R_{F2P}$)** | $$R_{F2P} = \frac{\text{Tests failing in baseline that pass in candidate}}{\text{Total baseline failing tests}}$$ | SWE-bench Protocol [Jimenez et al., 2024] | **[T1]** | Pilot: 3/3 passed (N=3). |
| **M1.3** | **Pass-to-Pass Preservation ($R_{P2P}$)** | $$R_{P2P} = \frac{\text{Existing passing tests still passing}}{\text{Total existing passing tests}}$$ | SWE-bench Protocol [Jimenez et al., 2024] | **[T1]** | Enforced locally (N=3). |
| **M1.4** | **Pass@$k$ Metric** | $$\text{Pass}@k = \mathbb{E}\left[ 1 - \frac{\binom{n-c}{k}}{\binom{n}{k}} \right]$$ | Standard [Chen et al., 2021] | **[N/A]** | N/A — Single-sample trajectory harness. |
| **M1.5** | **Plausibility vs. Correctness** | $$\text{PCR} = \frac{\text{Passes explicitly supplied issue-reproduction tests}}{\text{Passes completely hidden/held-out regression suite}}$$ | [Proposed metric] | **[T0]** | Untested. |
| **M1.6** | **Reproducibility ($REP$)** | $$REP = 1 - \left( \frac{\sigma_{\text{across 3 seeds}}}{\mu_{\text{across 3 seeds}}} \right)$$ | [Proposed metric] | **[T0]** | Untested. |
| **M1.7** | **Model Ablation Delta ($MAD$)** | $$MAD = RR(\text{harness} + \text{model}) - RR(\text{model alone})$$ | [Proposed metric] | **[T0]** | Untested. |

---

### Dimension 2: Context Economics & Retrieval Efficiency

Evaluates how smartly the harness navigates the codebase without drowning the LLM in redundant tokens.

| Metric ID | Metric Name | Mathematical Definition / Formula | Industry Baseline | Tier | Rakshak Actual |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M2.1** | **Context Compression Ratio ($CCR$)** | $$CCR = \left( 1 - \frac{\text{Context Tokens Ingested}}{\text{Eligible Full Source Tokens}} \right) \times 100$$ | 60%–75% [SWE-agent/Aider defaults, 2024] | **[T1]** | Pilot: 99.3% on synthetic fixtures (N=3). |
| **M2.2** | **Retrieval Hit Rate ($RHR@K$)** | $$\mathbb{I}(\text{Faulty Symbol / Line} \in \text{Top-}K \text{ Context})$$ | [Proposed metric] | **[T1]** | Pilot: 100% on synthetic fixtures (N=3). |
| **M2.3** | **Cost per Resolved Issue (CPRI)** | $$CPRI = \frac{\sum (\text{Input Tokens} \times P_{\text{in}} + \text{Output Tokens} \times P_{\text{out}})}{N_{\text{resolved}}}$$ | $0.80–$3.50 [Aider, 2024] | **[T1]** | Pilot: ~$0.02 per fixture (N=3, DeepSeek pricing). |
| **M2.4** | **Prompt-to-Patch Token Ratio** | $$PPTR = \frac{\text{Total Input Tokens}}{\text{Patch Diff Tokens}}$$ | [Proposed metric] | **[T1]** | Pilot: <15:1 on synthetic fixtures (N=3). |

---

### Dimension 3: Safety, Integrity & Anti-Tamper Governance

Measures defense against LLM "cheating" (e.g., deleting unit tests to make builds green) and environmental hygiene.

| Metric ID | Metric Name | Definition & Enforcement Method | Standard Agent Behavior | Tier | Rakshak Implementation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M3.1** | **Anti-Tamper Enforcement Rate ($ATER$)** | Rate of rejecting edits directed at `tests/`, `conftest.py`, or build configs | [Unregulated in SWE-agent defaults] | **[T1]** | Pilot: 100% architecturally enforced (N=47 internal pipeline tests). |
| **M3.2** | **No-Op / Hallucinated Edit Rejection** | $$NER = \frac{\text{Rejected empty or phantom patches}}{\text{Total attempted empty patches}}$$ | [Unregulated in SWE-bench base harness] | **[T1]** | Pilot: 100% architecturally enforced (N=47 internal pipeline tests). |
| **M3.3** | **Baseline Reproduction Fidelity ($BRF$)** | Verifies bug reproduces in clean checkout *before* synthesizing patch | [Unregulated in standard agent loops] | **[T1]** | Pilot: 100% architecturally enforced (N=47 internal pipeline tests). |
| **M3.4** | **Zero-Working-Tree Mutation ($ZWTM$)** | Original host repo remains bit-for-bit clean until human explicit confirmation | [Variable — Aider mutates locally] | **[T1]** | Pilot: 100% enforced via `git clone --no-hardlinks`. |
| **M3.5** | **Injection Resistance ($INJ$)** | $$INJ = 1 - \frac{\text{successful\_injections}}{\text{total\_injection\_trials}}$$ (Requires 50 adversarial repos) | [Proposed metric] | **[T0]** | Untested. |

---

### Dimension 4: Code Quality & Blast Radius (Semantic Precision)

Evaluates whether the patch is clean, idiomatic, and minimal rather than generating messy collateral changes.

| Metric ID | Metric Name | Mathematical Definition / Formula | Industry Baseline | Tier | Rakshak Actual |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M4.1** | **Normalized Blast Radius ($NBR$)** | $$NBR = \frac{\text{Lines of Code Changed by Patch}}{\text{Minimal Ground-Truth Fix LOC}}$$ | [Proposed threshold — 1.0–1.3] | **[T0]** | Untested. |
| **M4.2** | **AST Syntax Validity Rate ($SVR$)** | $$SVR = \frac{\text{Patches passing AST parse}}{\text{Total patches proposed}} \times 100$$ | [Proposed threshold — 100%] | **[T0]** | Untested. |
| **M4.3** | **CodeBLEU Semantic Score** | $$\text{CodeBLEU} = \alpha \cdot \text{BLEU} + \beta \cdot \text{BLEU}_{\text{weight}} + \gamma \cdot \text{Match}_{\text{AST}} + \delta \cdot \text{Match}_{\text{DF}}$$ | Standard metric [CodeXGLUE, 2021] | **[T0]** | Untested. |
| **M4.4** | **Cyclomatic Complexity Delta ($\Delta CC$)** | $$\Delta CC = CC(\text{code}_{\text{after}}) - CC(\text{code}_{\text{before}})$$ | [Proposed threshold — $\le +1$] | **[T0]** | Untested. |

---

### Dimension 5: Operational Performance & Observability

Evaluates runtime responsiveness, timeout handling, and telemetry.

| Metric ID | Metric Name | Definition & Metric Threshold | Industry Baseline | Tier | Rakshak Actual |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **M5.1** | **Time to Resolution (TTR)** | Median and 95th percentile seconds to verified candidate | [Proposed metric] | **[T1]** | Pilot: ~0.65s with local fixture mock (no network). Live-provider latency ~5-15s (Untested at scale). |
| **M5.2** | **Malformed JSON Recovery ($MJRR$)** | Recovery percentage when model returns broken JSON formatting | [Proposed metric] | **[T0]** | Untested. |
| **M5.3** | **Telemetry Completeness ($TCS$)** | Prometheus metrics export coverage (tokens, durations, status) | [Proposed metric] | **[T1]** | Pilot: 100% covered (`/metrics` endpoint). |

---

## 3. The Unified "Rakshak Harness Index" (RHI)

To synthesize these metrics into a single composite score, comparable across harnesses evaluated under this framework, we use a dimension-weighted composite function. This ensures that a model cannot simply game one metric (e.g., token efficiency) while failing completely on safety or quality.

```python
# Dimension-Level Subscores
D1 = 0.50 * RR_norm + 0.30 * F2P_norm + 0.20 * P2P_norm          # Functional Correctness
D2 = 0.50 * CCR_norm + 0.30 * CPRI_norm + 0.20 * RHR_norm        # Context Economics
D3 = 0.40 * ATER + 0.30 * ZWTM + 0.30 * NER                      # Safety & Governance
D4 = 0.50 * SVR + 0.30 * max(0, 100 - abs(NBR - 1.0)*100) + 0.20 * dCC_norm # Code Quality
# Note: dCC_norm maps delta cyclomatic complexity to [0,100] where delta <= 0 maps to 100, and positive deltas penalize linearly.
D5 = 0.50 * TTR_norm + 0.30 * MJRR + 0.20 * TCS                  # Operational Performance

# Final Composite Index
RHI = 0.35 * D1 + 0.20 * D3 + 0.15 * D2 + 0.15 * D4 + 0.15 * D5
```

### Weight Sensitivity & Robustness
Evaluators frequently criticize composite indexes for having arbitrary weights. **Weight sensitivity is currently untested.** We plan to conduct a Monte Carlo analysis (±10% weight perturbation, Spearman rank stability test) to mathematically guarantee that RHI reflects underlying capability, not arbitrary weight-tuning bias, once $\ge 3$ agents have been completely scored under RHI.

### Component Ablation Protocol (Isolating Harness Value)
To definitively prove that the Rakshak harness adds independent engineering value (rather than just acting as a passthrough for a smart LLM), we define a strict ablation protocol:

1. **Fix Variables:** Lock the underlying model, provider, and temperature (e.g., `gpt-4o`, temp=0).
2. **Establish Baseline:** Run the full harness on the SWE-bench Verified dataset ($N=300$).
3. **Component Ablation:** Disable one harness feature at a time and re-run:
   - Without AST-anchored lexical slicing (fallback to whole files).
   - Without the Syntax/AST validity pre-check gate.
   - Without the Baseline Pre-verification (No-op) gate.
   - Without the Iterative Test-Driven Retry loop.
4. **Report $\Delta RR$:** Calculate the drop in Resolve Rate (RR) for each ablation.

*Reporting this Model Ablation Delta ($MAD$) shifts the evaluation from "here's what we built" to mathematically proving "here's what actually matters."*

---

## 4. How to Reproduce & Score Locally

Run the automated evaluation pipeline already built in Rakshak:

```bash
# 1. Run synthetic microbenchmark measuring Context Compression (M2.1) & Verification (M1.1)
python3 benchmark.py --output evidence/microbenchmark.json

# 2. Run multi-task evaluation against live or mock models
python3 evaluate.py --manifest evaluation.example.json --output build/eval_summary

# 3. Inspect Prometheus runtime telemetry
curl http://localhost:9108/metrics
```
