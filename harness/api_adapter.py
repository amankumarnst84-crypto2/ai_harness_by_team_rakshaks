"""Groq, DeepSeek, and Qwen/campus chat-completions adapter, with no SDK dependency."""
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASES = {"groq": "https://api.groq.com/openai/v1", "deepseek": "https://api.deepseek.com"}
KEYS = {"groq": "GROQ_API_KEY", "deepseek": "DEEPSEEK_API_KEY", "qwen": "DASHSCOPE_API_KEY", "compatible": "HARNESS_API_KEY"}


def configuration(provider, base, model, key):
    if provider not in KEYS:
        raise ValueError("Choose Groq, DeepSeek, Qwen, or a compatible endpoint")
    if not all(isinstance(v, str) for v in (model, key)):
        raise ValueError("Model and API key must be strings")
    base = (base or BASES.get(provider, "")).strip().rstrip("/")
    url = urllib.parse.urlparse(base)
    local = url.hostname in {"127.0.0.1", "localhost", "::1"}
    if not url.hostname or not (url.scheme == "https" or (url.scheme == "http" and local)):
        raise ValueError("API base URL must use HTTPS, or HTTP on localhost")
    if url.username or url.password or url.query or url.fragment:
        raise ValueError("API base URL cannot contain credentials, queries, or fragments")
    if not model.strip() or len(model) > 200:
        raise ValueError("Enter the exact model ID supplied by your provider or college")
    if not key.strip() and not local:
        raise ValueError("An API key is required for this hosted endpoint")
    if len(key) > 4096 or any(c in key for c in "\r\n"):
        raise ValueError("Invalid API key")
    return {"HARNESS_PROVIDER": provider, "HARNESS_API_BASE": base,
            "HARNESS_MODEL": model.strip(), "HARNESS_API_KEY": key.strip()}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("API redirects are disabled; use the final API base URL")


def call_api(base, key, path, payload=None, retries=1):
    headers = {"Content-Type": "application/json", "User-Agent": "AI-Harness/2"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(base + path, data=None if payload is None else json.dumps(payload).encode(), headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=90 if payload else 15) as response:
            raw = response.read(1000001)
    except urllib.error.HTTPError as exc:
        if exc.code == 429 and retries > 0:
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            try:
                wait_time = min(15.0, max(1.0, float(retry_after))) if retry_after else 3.0
            except (ValueError, TypeError):
                wait_time = 3.0
            time.sleep(wait_time)
            return call_api(base, key, path, payload=payload, retries=retries - 1)
        hint = {401: "API key was rejected", 403: "model or API access denied", 404: "check API base URL and model ID", 429: "rate or quota limit reached"}.get(exc.code, "provider rejected request; check model and JSON-mode support")
        code = exc.code
        detail = ""
        if code != 401:
            try:
                body = exc.read(4096)
                if body:
                    try:
                        parsed = json.loads(body.decode("utf-8", "ignore"))
                        if isinstance(parsed, dict):
                            err_val = parsed.get("error")
                            if isinstance(err_val, dict):
                                detail = str(err_val.get("message") or err_val)
                            elif isinstance(err_val, str):
                                detail = err_val
                            elif "message" in parsed:
                                detail = str(parsed["message"])
                            elif "detail" in parsed:
                                detail = str(parsed["detail"])
                    except (ValueError, UnicodeDecodeError):
                        pass
            except OSError:
                pass
        exc.close()
        if detail:
            clean_detail = " ".join(detail.split())
            if not any(w in clean_detail.lower() for w in ("bearer", "sk-", "key=")):
                hint = clean_detail
        raise ValueError("Provider HTTP %s: %s" % (code, hint)) from None
    except urllib.error.URLError:
        raise ValueError("Could not connect to the configured API endpoint") from None
    if len(raw) > 1000000:
        raise ValueError("Provider response exceeds 1MB")
    return json.loads(raw)


def complete(request, env):
    payload = {"model": env["HARNESS_MODEL"], "stream": False,
               "messages": [{"role": "system", "content": request["instruction"]},
                            {"role": "user", "content": json.dumps({k: v for k, v in request.items() if k != "instruction"})}],
               "response_format": {"type": "json_object"}}
    payload["temperature"] = 0
    # Keep text-only non-thinking calls bounded; never silently substitute models.
    if env["HARNESS_PROVIDER"] == "deepseek" and env["HARNESS_MODEL"].startswith(("deepseek-v4", "deepseek-flash")):
        payload["thinking"] = {"type": "disabled"}
        payload["effort"] = {"level": "low"}
    cap_field = "max_completion_tokens" if env["HARNESS_PROVIDER"] == "groq" else "max_tokens"
    payload[cap_field] = min(2048, int(request.get("max_output_tokens", 1500)))
    try:
        result = call_api(env["HARNESS_API_BASE"], env["HARNESS_API_KEY"], "/chat/completions", payload)
    except ValueError as exc:
        err_msg = str(exc)
        if "HTTP 400" in err_msg:
            # Automatic schema resilience for endpoints rejecting optional parameters
            retried = False
            if "thinking" in payload:
                payload.pop("thinking", None)
                try:
                    result = call_api(env["HARNESS_API_BASE"], env["HARNESS_API_KEY"], "/chat/completions", payload)
                    retried = True
                except ValueError as exc2:
                    exc, err_msg = exc2, str(exc2)
            if not retried and "response_format" in payload:
                payload.pop("response_format", None)
                try:
                    result = call_api(env["HARNESS_API_BASE"], env["HARNESS_API_KEY"], "/chat/completions", payload)
                    retried = True
                except ValueError as exc3:
                    exc, err_msg = exc3, str(exc3)
            if not retried and payload.get(cap_field, 0) > 1024:
                payload[cap_field] = 1024
                try:
                    result = call_api(env["HARNESS_API_BASE"], env["HARNESS_API_KEY"], "/chat/completions", payload)
                    retried = True
                except ValueError as exc4:
                    exc = exc4
            if not retried:
                raise exc
        else:
            raise exc
    usage = result.get("usage") or {}
    reported = {}
    if all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens")):
        reported = {"input_tokens": usage["prompt_tokens"], "output_tokens": usage["completion_tokens"]}
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", usage.get("prompt_cache_hit_tokens"))
        if type(cached) is int and cached >= 0:
            reported["cached_input_tokens"] = cached
    choice = result["choices"][0]
    if choice.get("finish_reason") == "length":
        return {"plan": "Provider output reached the configured cap before completion.",
                "adapter_error": "Output was truncated. Retry one small edit to one file, not a full rewrite.", "edits": [], "usage": reported}
    raw_content = choice["message"]["content"].strip()
    if raw_content.startswith("```"):
        raw_content = re.sub(r"^```(?:json)?\s*", "", raw_content, flags=re.I)
        raw_content = re.sub(r"\s*```$", "", raw_content).strip()
    try:
        answer = json.loads(raw_content)
        if not isinstance(answer, dict):
            raise ValueError("Expected object")
    except (TypeError, ValueError):
        return {"plan": "Provider returned invalid JSON. Retry with a complete JSON edit object.",
                "adapter_error": "Invalid JSON. Retry one small edit to one file using valid JSON.", "edits": [], "usage": reported}
    answer["usage"] = reported
    return answer


def main():
    request = json.loads(Path(sys.argv[-1]).read_text())
    provider = os.environ.get("HARNESS_PROVIDER", "groq")
    env = configuration(provider, os.environ.get("HARNESS_API_BASE"), os.environ.get("HARNESS_MODEL", ""),
                        os.environ.get("HARNESS_API_KEY", os.environ.get("AI_API_KEY", os.environ.get(KEYS.get(provider, ""), ""))))
    print(json.dumps(complete(request, env)))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, IndexError, TypeError, OSError) as exc:
        print("Model API: " + str(exc), file=sys.stderr)
        sys.exit(2)
