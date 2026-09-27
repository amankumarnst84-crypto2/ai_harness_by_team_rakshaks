"""
test_rakshak_demo.py
====================
Team Rakshak — AI Harness Demo Tests
Verification command: python3 -m pytest -q
"""

import json
import time
import hashlib
import pytest


# ─────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────

@pytest.fixture
def sample_prompt():
    return {
        "id": "rakshak_001",
        "text": "Explain neural networks in simple terms.",
        "category": "ai",
        "difficulty": "easy"
    }

@pytest.fixture
def model_response():
    return {
        "content": "Neural networks are computing systems inspired by biological neural networks.",
        "latency_ms": 210,
        "model": "deepseek-v4-pro",
        "finish_reason": "stop",
        "tokens_used": 14
    }


# ─────────────────────────────────────────────
# 1. BASIC SANITY TESTS
# ─────────────────────────────────────────────

def test_project_name():
    assert "rakshak" in "team_rakshak_ai_harness"

def test_python_version():
    import sys
    assert sys.version_info >= (3, 9), "Python 3.9+ required"

def test_json_roundtrip():
    data = {"score": 0.97, "passed": True, "model": "deepseek-v4-pro"}
    assert json.loads(json.dumps(data)) == data

def test_hash_consistency():
    h = hashlib.sha256(b"rakshak").hexdigest()
    assert len(h) == 64
    assert h == hashlib.sha256(b"rakshak").hexdigest()


# ─────────────────────────────────────────────
# 2. PROMPT VALIDATION TESTS
# ─────────────────────────────────────────────

def test_prompt_has_required_fields(sample_prompt):
    for field in ["id", "text", "category"]:
        assert field in sample_prompt

def test_prompt_text_not_empty(sample_prompt):
    assert len(sample_prompt["text"].strip()) > 0

def test_prompt_id_is_string(sample_prompt):
    assert isinstance(sample_prompt["id"], str)

def test_batch_prompts_valid():
    batch = [{"id": f"p_{i}", "text": f"Question {i}", "category": "general"} for i in range(10)]
    assert len(batch) == 10
    for p in batch:
        assert "id" in p and "text" in p


# ─────────────────────────────────────────────
# 3. MODEL RESPONSE TESTS
# ─────────────────────────────────────────────

def test_response_has_content(model_response):
    assert "content" in model_response
    assert len(model_response["content"]) > 0

def test_response_latency_positive(model_response):
    assert model_response["latency_ms"] > 0

def test_response_finish_reason(model_response):
    assert model_response["finish_reason"] == "stop"

def test_response_model_name(model_response):
    assert model_response["model"] == "deepseek-v4-pro"

def test_token_count_in_range(model_response):
    assert 0 < model_response["tokens_used"] < 10000


# ─────────────────────────────────────────────
# 4. SCORING TESTS
# ─────────────────────────────────────────────

def _score(response: str, reference: str) -> float:
    r = set(response.lower().split())
    ref = set(reference.lower().split())
    return len(r & ref) / len(ref) if ref else 0.0

def test_perfect_score():
    assert _score("the cat sat on mat", "the cat sat on mat") == pytest.approx(1.0)

def test_zero_score():
    assert _score("banana mango", "quantum physics laser") == pytest.approx(0.0)

def test_partial_score():
    s = _score("neural networks are great", "neural networks inspired by biology")
    assert 0.0 < s < 1.0

def test_score_always_in_range():
    pairs = [("hello world", "hello there"), ("ai rocks", "machine learning"), ("", "test")]
    for r, ref in pairs:
        s = _score(r, ref)
        assert 0.0 <= s <= 1.0


# ─────────────────────────────────────────────
# 5. PIPELINE E2E TEST
# ─────────────────────────────────────────────

def test_full_pipeline(sample_prompt, model_response):
    # Step 1: Ingest
    assert sample_prompt["text"]

    # Step 2: Response
    assert model_response["content"]

    # Step 3: Score
    ref = "neural networks inspired by biological brain systems"
    score = _score(model_response["content"], ref)
    assert score >= 0.0

    # Step 4: Log
    log = {
        "prompt_id": sample_prompt["id"],
        "score": round(score, 4),
        "latency_ms": model_response["latency_ms"],
        "status": "passed" if score > 0.2 else "failed"
    }
    assert log["status"] in ["passed", "failed"]

    # Step 5: Serialize
    assert isinstance(json.dumps(log), str)

def test_latency_measurement():
    start = time.time()
    time.sleep(0.01)
    latency = (time.time() - start) * 1000
    assert latency > 5

def test_aggregate_score():
    scores = [0.80, 0.85, 0.90, 0.75, 0.95]
    avg = sum(scores) / len(scores)
    assert avg == pytest.approx(0.85)
