"""Standalone adapter: python /absolute/path/ollama_adapter.py request.json."""
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request


def main():
    request = json.loads(Path(sys.argv[-1]).read_text())
    model = os.environ.get("HARNESS_MODEL", "")
    if not model:
        raise ValueError("Set HARNESS_MODEL to an installed Ollama model")
    payload = {"model": model, "stream": False, "format": "json",
               "messages": [{"role": "system", "content": request["instruction"]},
                            {"role": "user", "content": json.dumps({k: v for k, v in request.items() if k != "instruction"})}],
               "options": {"temperature": 0, "num_predict": request.get("max_output_tokens", 1500)}}
    url = os.environ.get("HARNESS_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/") + "/api/chat"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as response:
        raw = response.read(1000001)
    if len(raw) > 1000000:
        raise ValueError("Model response exceeds 1MB")
    result = json.loads(raw)
    answer = json.loads(result["message"]["content"])
    if not isinstance(answer, dict):
        raise ValueError("Model must return a JSON object")
    if all(type(result.get(k)) is int for k in ("prompt_eval_count", "eval_count")):
        answer["usage"] = {"input_tokens": result["prompt_eval_count"], "output_tokens": result["eval_count"]}
    print(json.dumps(answer))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, urllib.error.URLError) as exc:
        print("Ollama: " + str(exc), file=sys.stderr)
        sys.exit(2)
