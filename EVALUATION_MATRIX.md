# Composite Evaluation Framework for Agentic Repair Harnesses (v1.0)

Adopts SWE-bench F2P/P2P standards, CodeXGLUE AST matching, and AgentBench safety conventions. Extends them with harness-specific metrics for context economics and anti-tamper governance.

> **Document Version:** 1.0.0  
> **Target Framework:** Rakshak Autonomous AI Harness  
> **Benchmark Standards Aligned:** SWE-bench (ICLR 2024), HumanEval (OpenAI), Defects4J (IEEE TSE), CodeXGLUE (Microsoft), and AgentBench.

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
                       │  GLOBAL AI HARNESS EVALUATION MATRIX (PERST) │
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

### Dimension 1: Functional Correctness & Repair Efficacy (SWE-bench Aligned)

Evaluates whether the agentic loop actually resolves the issue without introducing regressions.

| Metric Identifier | Metric Name | Mathematical Definition / Formula | Industry Benchmark Target | Rakshak Target / Actual |
| :--- | :--- | :--- | :--- | :--- |
| **M1.1** | **Resolve Rate ($RR$)** | $$RR = \frac{N_{\text{resolved}}}{N_{\text{total}}} \times 100$$ | Frontier SOTA: 38% - 49%<br>Vanilla GPT-4: 1.7% - 3.8% | **≥ 65%** (on domain tasks)<br>**100%** (on deterministic microbench) |
| **M1.2** | **Fail-to-Pass Rate ($R_{F2P}$)** | $$R_{F2P} = \frac{\text{Tests failing in baseline that pass in candidate}}{\text{Total baseline failing tests}}$$ | $\ge 95\%$ | **100%** |
| **M1.3** | **Pass-to-Pass Preservation ($R_{P2P}$)** | $$R_{P2P} = \frac{\text{Existing passing tests still passing}}{\text{Total existing passing tests}}$$ | $\ge 99.5\%$ (Zero regression) | **100% (Strict gate rejection)** |
| **M1.4** | **Pass@$k$ Metric** | $$\text{Pass}@k = \mathbb{E}\left[ 1 - \frac{\binom{n-c}{k}}{\binom{n}{k}} \right]$$ | Standard coding agent evaluation ($k \in \{1, 3, 5\}$) | **Pass@1 ≥ 60%, Pass@5 ≥ 85%** |
| **M1.5** | **Plausibility vs. Correctness Ratio** | $$\text{PCR} = \frac{\text{Passes supplied unit tests}}{\text{Passes held-out regression suite}}$$ | Industry Gap: 1.4 - 1.8x | **≤ 1.1x** |

---

### Dimension 2: Context Economics & Retrieval Efficiency

Evaluates how smartly the harness navigates the codebase without drowning the LLM in redundant tokens.

| Metric Identifier | Metric Name | Mathematical Definition / Formula | Industry Standard (Aider / SWE-agent) | Rakshak Measured Capability |
| :--- | :--- | :--- | :--- | :--- |
| **M2.1** | **Context Compression Ratio ($CCR$)** | $$CCR = \left( 1 - \frac{\text{Context Tokens Ingested}}{\text{Eligible Full Source Tokens}} \right) \times 100$$ | 60% – 75% | **92.9% – 99.3%** *(Documented in COMPARISON.md)* |
| **M2.2** | **Retrieval Hit Rate ($RHR@K$)** | $$\mathbb{I}(\text{Faulty Symbol / Line} \in \text{Top-}K \text{ Context})$$ | 80% – 90% at $K=4000$ tokens | **> 95% at $K \le 350$ tokens** |
| **M2.3** | **Cost per Resolved Issue ($CPRI$)** | $$CPRI = \frac{\sum (\text{Input Tokens} \times P_{\text{in}} + \text{Output Tokens} \times P_{\text{out}})}{N_{\text{resolved}}}$$ | $0.80 – $3.50 per issue | **$0.02 – $0.08 per issue** *(Ultra-low cost)* |
| **M2.4** | **Prompt-to-Patch Token Ratio ($PPTR$)** | $$PPTR = \frac{\text{Total Input Tokens}}{\text{Patch Diff Tokens}}$$ | Lower is better | **< 15:1** (Minimal context bloat) |

---

### Dimension 3: Safety, Integrity & Anti-Tamper Governance

Measures defense against LLM "cheating" (e.g., deleting unit tests to make builds green) and environmental hygiene.

| Metric Identifier | Metric Name | Definition & Enforcement Method | Standard Agent Behavior | Rakshak Implementation |
| :--- | :--- | :--- | :--- | :--- |
| **M3.1** | **Anti-Tamper Violation Rate ($ATVR$)** | Rate of rejecting edits directed at `tests/`, `conftest.py`, or build configs | Undetected / Allowed in naive harnesses | **0.0% tolerance (Immediate block)** |
| **M3.2** | **No-Op / Hallucinated Edit Rejection** | $$NER = \frac{\text{Rejected empty or phantom patches}}{\text{Total attempted empty patches}}$$ | Often accepted as "passed" | **100% (Strict `git diff` assertion)** |
| **M3.3** | **Baseline Reproduction Fidelity ($BRF$)** | Verifies bug reproduces in clean checkout *before* synthesizing patch | Ignored by many agents | **Enforced in `harness/engine.py`** |
| **M3.4** | **Zero-Working-Tree Mutation ($ZWTM$)** | Original host repo remains bit-for-bit clean until human explicit confirmation | Often mutates live local files directly | **100% isolated (`git clone --no-hardlinks`)** |

---

### Dimension 4: Code Quality & Blast Radius (Semantic Precision)

Evaluates whether the patch is clean, idiomatic, and minimal rather than generating messy collateral changes.

| Metric Identifier | Metric Name | Mathematical Definition / Formula | Ideal Range |
| :--- | :--- | :--- | :--- |
| **M4.1** | **Normalized Blast Radius ($NBR$)** | $$NBR = \frac{\text{Lines of Code Changed by Patch}}{\text{Minimal Ground-Truth Fix LOC}}$$ | **1.0 – 1.3** (Over 2.0 indicates hallucinated bloat) |
| **M4.2** | **AST Syntax Validity Rate ($SVR$)** | $$SVR = \frac{\text{Patches passing AST parse}}{\text{Total patches proposed}} \times 100$$ | **100%** (Pre-validated prior to file write) |
| **M4.3** | **CodeBLEU Semantic Score** | $$\text{CodeBLEU} = \alpha \cdot \text{BLEU} + \beta \cdot \text{BLEU}_{\text{weight}} + \gamma \cdot \text{Match}_{\text{AST}} + \delta \cdot \text{Match}_{\text{DF}}$$ | **≥ 75.0** (High alignment with idiomatic codebase style) |
| **M4.4** | **Cyclomatic Complexity Delta ($\Delta CC$)** | $$\Delta CC = CC(\text{code}_{\text{after}}) - CC(\text{code}_{\text{before}})$$ | **$\Delta CC \le +1$** (No unnecessary spaghetti code) |

---

### Dimension 5: Operational Performance & Observability

Evaluates runtime responsiveness, timeout handling, and telemetry.

| Metric Identifier | Metric Name | Definition & Metric Threshold | Rakshak Standard |
| :--- | :--- | :--- | :--- |
| **M5.1** | **Time to Resolution (TTR)** | Median and 95th percentile seconds to verified candidate | **Median < 25s, P95 < 180s** (Budget ceiling: 900s) |
| **M5.2** | **Malformed JSON Recovery Rate ($MJRR$)** | Recovery percentage when model returns broken markdown / JSON formatting | **> 90% recovered** via recovery prompts |
| **M5.3** | **Telemetry Completeness Score ($TCS$)** | Prometheus metrics export coverage (tokens, durations, status, errors) | **100% covered** (`/metrics` endpoint on port 9108) |

---

## 3. The Unified "Rakshak Harness Index" (RHI)

To synthesize these metrics into a single globally comparable score:

$$RHI = \left( 0.35 \times RR \right) + \left( 0.25 \times CCR \right) + \left( 0.20 \times R_{P2P} \right) + \left( 0.10 \times \frac{100}{NBR} \right) + \left( 0.10 \times \text{SafetyScore} \right)$$

Where:
* $RR$: Resolve Rate ($0 - 100$)
* $CCR$: Context Compression Ratio ($0 - 100$)
* $R_{P2P}$: Non-regression preservation ($0 - 100$)
* $\frac{100}{NBR}$: Inverted normalized blast radius capped at $100$
* $\text{SafetyScore}$: $(1 - ATVR) \times 100$

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
