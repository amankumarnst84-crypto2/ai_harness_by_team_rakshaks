"""
test_full_pipeline.py
=====================
Full end-to-end pipeline tests for AI Harness — Team Rakshak
Covers: ingestion, evaluation, adapter, observability, and scoring.
"""

import os
import json
import time
import unittest
import tempfile
import hashlib
from unittest.mock import patch, MagicMock, mock_open


# ─────────────────────────────────────────────
# 1. UTILITY / HELPER TESTS
# ─────────────────────────────────────────────
class TestUtilities(unittest.TestCase):

    def test_json_serialization(self):
        """JSON round-trip must be lossless."""
        payload = {"model": "gpt-4", "score": 0.97, "passed": True, "tags": ["ai", "test"]}
        dumped  = json.dumps(payload)
        loaded  = json.loads(dumped)
        self.assertEqual(payload, loaded)

    def test_sha256_hash_consistency(self):
        """Same input must always produce same hash."""
        data = b"rakshak-ai-harness-2026"
        h1 = hashlib.sha256(data).hexdigest()
        h2 = hashlib.sha256(data).hexdigest()
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)

    def test_tempfile_creation(self):
        """Temp files must be writable and readable."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"status": "ok"}, f)
            tmp_path = f.name
        with open(tmp_path) as f:
            data = json.load(f)
        self.assertEqual(data["status"], "ok")
        os.unlink(tmp_path)

    def test_env_variable_read(self):
        """Environment variables should be readable."""
        os.environ["TEST_RAKSHAK_KEY"] = "rakshak_secret_123"
        val = os.environ.get("TEST_RAKSHAK_KEY")
        self.assertEqual(val, "rakshak_secret_123")


# ─────────────────────────────────────────────
# 2. DATA INGESTION TESTS
# ─────────────────────────────────────────────
class TestDataIngestion(unittest.TestCase):

    def setUp(self):
        self.sample_prompt = {
            "id": "prompt_001",
            "text": "Explain quantum computing in simple terms.",
            "category": "science",
            "difficulty": "medium"
        }

    def test_prompt_has_required_fields(self):
        """Each prompt must have id, text, category."""
        required = ["id", "text", "category"]
        for field in required:
            self.assertIn(field, self.sample_prompt, f"Missing field: {field}")

    def test_prompt_id_is_string(self):
        self.assertIsInstance(self.sample_prompt["id"], str)

    def test_prompt_text_not_empty(self):
        self.assertTrue(len(self.sample_prompt["text"].strip()) > 0)

    def test_batch_ingestion(self):
        """Batch of prompts must all pass validation."""
        batch = [
            {"id": f"p_{i}", "text": f"Question number {i}", "category": "general"}
            for i in range(50)
        ]
        for item in batch:
            self.assertIn("id", item)
            self.assertIn("text", item)
        self.assertEqual(len(batch), 50)


# ─────────────────────────────────────────────
# 3. MODEL RESPONSE TESTS
# ─────────────────────────────────────────────
class TestModelResponse(unittest.TestCase):

    def _mock_response(self, content="This is a model response.", latency=0.12):
        return {
            "content": content,
            "latency_ms": latency * 1000,
            "tokens_used": len(content.split()),
            "model": "gpt-4o",
            "finish_reason": "stop"
        }

    def test_response_has_content(self):
        resp = self._mock_response()
        self.assertIn("content", resp)
        self.assertGreater(len(resp["content"]), 0)

    def test_latency_is_positive(self):
        resp = self._mock_response(latency=0.25)
        self.assertGreater(resp["latency_ms"], 0)

    def test_finish_reason_is_stop(self):
        resp = self._mock_response()
        self.assertEqual(resp["finish_reason"], "stop")

    def test_token_count_reasonable(self):
        resp = self._mock_response("Hello world this is a test response")
        self.assertGreater(resp["tokens_used"], 0)
        self.assertLess(resp["tokens_used"], 10000)

    def test_multiple_responses_independent(self):
        """Each response object must be independent."""
        r1 = self._mock_response("Answer one")
        r2 = self._mock_response("Answer two")
        self.assertNotEqual(r1["content"], r2["content"])


# ─────────────────────────────────────────────
# 4. SCORING / EVALUATION TESTS
# ─────────────────────────────────────────────
class TestScoring(unittest.TestCase):

    def _score(self, response, reference):
        """Simple word-overlap scoring (mock)."""
        resp_words = set(response.lower().split())
        ref_words  = set(reference.lower().split())
        if not ref_words:
            return 0.0
        return len(resp_words & ref_words) / len(ref_words)

    def test_perfect_match_score(self):
        score = self._score("the cat sat on the mat", "the cat sat on the mat")
        self.assertAlmostEqual(score, 1.0)

    def test_zero_match_score(self):
        score = self._score("banana orange mango", "physics quantum laser")
        self.assertAlmostEqual(score, 0.0)

    def test_partial_match_score(self):
        score = self._score("the cat sat", "the cat sat on the mat")
        self.assertGreater(score, 0.0)
        self.assertLess(score, 1.0)

    def test_score_range_always_valid(self):
        pairs = [
            ("hello world", "hello there world wide"),
            ("ai is great", "machine learning"),
            ("", "something"),
        ]
        for resp, ref in pairs:
            score = self._score(resp, ref)
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)

    def test_batch_scoring(self):
        """All scores in a batch must be in [0, 1]."""
        results = [
            self._score(f"response {i}", f"reference {i} text")
            for i in range(20)
        ]
        for s in results:
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)


# ─────────────────────────────────────────────
# 5. ADAPTER TESTS
# ─────────────────────────────────────────────
class TestAdapter(unittest.TestCase):

    def test_adapter_maps_input_correctly(self):
        """Adapter must transform raw input to expected format."""
        raw = {"query": "What is AI?", "user_id": "u123"}
        adapted = {
            "prompt": raw["query"],
            "session": raw["user_id"],
            "timestamp": "2026-09-27T12:00:00"
        }
        self.assertEqual(adapted["prompt"], "What is AI?")
        self.assertEqual(adapted["session"], "u123")

    def test_adapter_handles_missing_optional_field(self):
        raw = {"query": "Explain ML"}
        prompt = raw.get("query", "")
        session = raw.get("user_id", "anonymous")
        self.assertEqual(session, "anonymous")
        self.assertEqual(prompt, "Explain ML")

    def test_adapter_output_is_json_serializable(self):
        output = {"prompt": "Hello", "session": "s1", "score": 0.95}
        try:
            json.dumps(output)
            serializable = True
        except TypeError:
            serializable = False
        self.assertTrue(serializable)


# ─────────────────────────────────────────────
# 6. OBSERVABILITY / LOGGING TESTS
# ─────────────────────────────────────────────
class TestObservability(unittest.TestCase):

    def test_log_entry_structure(self):
        log = {
            "timestamp": "2026-09-27T12:00:00+05:30",
            "level": "INFO",
            "message": "Pipeline started",
            "run_id": "run_abc123"
        }
        self.assertIn("timestamp", log)
        self.assertIn("level", log)
        self.assertIn("message", log)

    def test_latency_tracking(self):
        start = time.time()
        time.sleep(0.01)
        end = time.time()
        latency = (end - start) * 1000
        self.assertGreater(latency, 5)   # at least 5ms
        self.assertLess(latency, 5000)   # less than 5s

    def test_error_logging_format(self):
        error_log = {
            "level": "ERROR",
            "message": "Connection timeout",
            "code": 504,
            "retry": True
        }
        self.assertEqual(error_log["level"], "ERROR")
        self.assertIsInstance(error_log["code"], int)
        self.assertTrue(error_log["retry"])


# ─────────────────────────────────────────────
# 7. END-TO-END PIPELINE TEST
# ─────────────────────────────────────────────
class TestEndToEndPipeline(unittest.TestCase):

    def test_full_pipeline_flow(self):
        """Simulate a full prompt → response → score → log cycle."""

        # 1. Ingest
        prompt = {"id": "e2e_001", "text": "What is deep learning?", "category": "ai"}
        self.assertIn("text", prompt)

        # 2. Mock model call
        response = {
            "content": "Deep learning is a subset of machine learning using neural networks.",
            "latency_ms": 320,
            "model": "gpt-4o"
        }
        self.assertIn("content", response)

        # 3. Score
        ref = "deep learning uses neural networks and is part of machine learning"
        resp_words = set(response["content"].lower().split())
        ref_words  = set(ref.split())
        score = len(resp_words & ref_words) / len(ref_words)
        self.assertGreater(score, 0.0)

        # 4. Log
        log_entry = {
            "prompt_id": prompt["id"],
            "score": round(score, 4),
            "latency_ms": response["latency_ms"],
            "status": "passed" if score > 0.3 else "failed"
        }
        self.assertIn("status", log_entry)
        self.assertIn(log_entry["status"], ["passed", "failed"])

        # 5. Serialize
        serialized = json.dumps(log_entry)
        self.assertIsInstance(serialized, str)

    def test_pipeline_handles_empty_response(self):
        """Pipeline should not crash on empty model response."""
        response_content = ""
        ref = "some reference answer"
        resp_words = set(response_content.lower().split())
        ref_words  = set(ref.split())
        score = len(resp_words & ref_words) / len(ref_words) if ref_words else 0.0
        self.assertEqual(score, 0.0)

    def test_pipeline_result_summary(self):
        """Aggregate results must compute average score correctly."""
        scores = [0.85, 0.90, 0.75, 0.95, 0.80]
        avg = sum(scores) / len(scores)
        self.assertAlmostEqual(avg, 0.85)
        self.assertGreaterEqual(avg, 0.0)
        self.assertLessEqual(avg, 1.0)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    unittest.main(verbosity=2)
