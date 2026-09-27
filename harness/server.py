"""Loopback-only local workspace. Run only trusted repositories and commands."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
from urllib.parse import urlparse
import uuid

from .engine import run
from .fixtures import create_fixture
from .safety import Stop, clean
from .api_adapter import BASES, KEYS, call_api, configuration

STATIC = Path(__file__).parent / "web"


class Store:
    def __init__(self, directory, adapter=None, metrics_only=False, adapter_env=None):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.adapter = adapter
        self.adapter_env = adapter_env or {}
        self.lock = threading.RLock()
        self.jobs = {}
        self.active = None
        self.csrf = secrets.token_urlsafe(32)
        for path in sorted(self.directory.glob("*/meta.json")):
            try:
                job = json.loads(path.read_text())
                result = path.parent / "result"
                if metrics_only and not (result / "report.json").exists():
                    continue
                job["report"] = json.loads((result / "report.json").read_text()) if (result / "report.json").exists() else None
                job["status"] = job["report"]["status"] if job["report"] else "interrupted"
                job["events"] = [json.loads(line) for line in (result / "trace.jsonl").read_text().splitlines()] if not metrics_only and (result / "trace.jsonl").exists() else []
                self.jobs[job["id"]] = job
            except (ValueError, KeyError, OSError):
                continue

    def public_config(self):
        return {"csrf": self.csrf, "model_available": bool(self.adapter),
                "model": self.adapter_env.get("HARNESS_MODEL", os.environ.get("HARNESS_MODEL", "Custom adapter" if self.adapter else "Not configured")),
                "provider": self.adapter_env.get("HARNESS_PROVIDER", "groq"),
                "api_base": self.adapter_env.get("HARNESS_API_BASE", BASES["groq"]),
                "has_key": bool(self.adapter_env.get("HARNESS_API_KEY")),
                "grafana_url": "http://localhost:3001/d/harness/ai-harness", "python": sys.executable}

    def connection_env(self, data, listing=False):
        if not isinstance(data, dict):
            raise ValueError("Connection must be a JSON object")
        provider = data.get("provider", "groq")
        base = data.get("api_base", BASES.get(provider, ""))
        key = data.get("api_key", "")
        if not isinstance(base, str):
            raise ValueError("API base must be a string")
        if not key and base.strip().rstrip("/") == self.adapter_env.get("HARNESS_API_BASE") and provider == self.adapter_env.get("HARNESS_PROVIDER"):
            key = self.adapter_env.get("HARNESS_API_KEY", "")
        return configuration(provider, base, "model-list" if listing else data.get("model", ""), key)

    def configure(self, data):
        with self.lock:
            if self.active:
                raise ValueError("Wait for the active run before changing the model")
            if isinstance(data, dict) and data.get("disconnect") is True:
                self.adapter, self.adapter_env = None, {}
            else:
                self.adapter_env = self.connection_env(data)
                self.adapter = [sys.executable, str(Path(__file__).with_name("api_adapter.py"))]
            return self.public_config()

    def summaries(self):
        with self.lock:
            return [clean({k: v for k, v in j.items() if k not in {"cancel", "events"}})
                    for j in sorted(self.jobs.values(), key=lambda j: j["created"], reverse=True)]

    def detail(self, identity):
        with self.lock:
            if identity not in self.jobs:
                raise KeyError(identity)
            job = clean({k: v for k, v in self.jobs[identity].items() if k != "cancel"})
        path = self.directory / identity / "result" / "candidate.patch"
        job["patch"] = path.read_text() if path.exists() else ""
        return job

    def start(self, data):
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        mode = data.get("mode", "demo")
        if mode not in {"demo", "model"}:
            raise ValueError("Unknown model mode")
        if mode == "model" and not self.adapter:
            raise ValueError("No model configured. Restart with HARNESS_MODEL or --adapter.")
        issue = data.get("issue", "")
        if not isinstance(issue, str) or len(issue) > 12000:
            raise ValueError("Issue must contain at most 12000 characters")
        tokens, attempts = data.get("tokens", 12000), data.get("attempts", 5)
        if type(tokens) is not int or not 1000 <= tokens <= 200000:
            raise ValueError("Token budget must be 1000-200000")
        if type(attempts) is not int or not 1 <= attempts <= 20:
            raise ValueError("Attempts must be 1-20")
        if mode == "model":
            repo, test = data.get("repo"), data.get("test")
            if not isinstance(repo, str) or not Path(repo).is_dir() or not issue.strip():
                raise ValueError("A repository directory and issue are required")
            if not isinstance(test, list) or not test or len(test) > 32 or not all(isinstance(x, str) and x for x in test):
                raise ValueError("Test command must be a nonempty JSON string array")
        with self.lock:
            if self.active:
                raise ValueError("A run is already active. Stop it or wait for completion.")
            identity = uuid.uuid4().hex[:12]
            directory = self.directory / identity
            directory.mkdir()
            if mode == "demo":
                fixture = create_fixture(directory / "fixture")
                repo, test, mock = fixture["repo"], fixture["test"], fixture["mock"]
                issue = fixture["issue"]
            else:
                mock = None
            job = {"id": identity, "created": datetime.now(timezone.utc).isoformat(), "issue": issue,
                   "repo": repo, "mode": mode, "status": "running", "events": [], "report": None,
                   "tokens": tokens, "attempts": attempts, "test": test, "cancel": threading.Event()}
            adapter, adapter_env = self.adapter, dict(self.adapter_env)
            job["model"] = "fixture" if mode == "demo" else self.public_config()["model"]
            self.jobs[identity] = job
            self.active = identity
            (directory / "meta.json").write_text(json.dumps(clean({k: v for k, v in job.items() if k not in {"cancel", "events"}})))

        def on_event(event):
            with self.lock:
                job["events"].append(event)

        def worker():
            args = argparse.Namespace(repo=repo, issue=issue, test=test, mock=mock, adapter=adapter,
                                      adapter_env=adapter_env, model_label=job["model"],
                                      output=str(directory / "result"), attempts=attempts, tokens=tokens,
                                      seconds=300, command_seconds=120, max_output_tokens=1500, context_chars=10000,
                                      quiet=True, cancel=job["cancel"], on_event=on_event)
            try:
                run(args)
                report = json.loads((directory / "result" / "report.json").read_text())
                with self.lock:
                    job["report"], job["status"] = report, report["status"]
            except Exception as exc:
                with self.lock:
                    job["status"] = "error"
                    job["report"] = clean({"status": "error", "error": str(exc), "mode": "simulation" if mock else "model_adapter"})
                    (directory / "result").mkdir(exist_ok=True)
                    (directory / "result" / "report.json").write_text(json.dumps(job["report"]))
            finally:
                with self.lock:
                    self.active = None

        threading.Thread(target=worker, daemon=True, name="harness-" + identity).start()
        return identity

    def cancel(self, identity):
        with self.lock:
            if identity not in self.jobs:
                raise KeyError(identity)
            if self.jobs[identity]["status"] != "running":
                raise ValueError("Run has already finished")
            self.jobs[identity]["cancel"].set()

    def metrics(self, include_active=True):
        jobs = self.summaries()
        lines = ["# HELP harness_runs_total Completed debugging runs by outcome and execution mode.",
                 "# TYPE harness_runs_total counter"]
        for mode in ("demo", "model"):
            for status in ("verified_candidate", "tests_pass_candidate", "unverified_candidate", "incomplete", "cancelled", "error", "interrupted"):
                lines.append('harness_runs_total{mode="%s",status="%s"} %d' % (mode, status, sum(j["mode"] == mode and j["status"] == status for j in jobs)))
        for metric, field in (("tokens_estimated", "estimated_tokens"), ("input_tokens_estimated", "input_tokens_estimate"),
                              ("output_tokens_estimated", "output_tokens_estimate"), ("provider_input_tokens", "provider_input_tokens"),
                              ("provider_output_tokens", "provider_output_tokens"), ("context_tokens_avoided_estimated", "context_tokens_avoided_estimate"),
                              ("context_full_tokens_estimated", "context_full_tokens_estimate"), ("duration_seconds", "elapsed_seconds"), ("model_calls", "model_calls"), ("provider_usage_calls", "provider_usage_calls")):
            name = "harness_" + metric + "_total"
            lines.extend(["# HELP " + name + " Cumulative values from completed reports.", "# TYPE " + name + " counter"])
            for mode in ("demo", "model"):
                value = sum((j.get("report") or {}).get(field, 0) for j in jobs if j["mode"] == mode)
                lines.append('%s{mode="%s"} %s' % (name, mode, value))
        by_model = defaultdict(lambda: {"runs": 0, "verified": 0, "tokens": 0, "reported": 0})
        for job in jobs:
            report = job.get("report") or {}
            if not report:
                continue
            key = (job["mode"], str(report.get("provider", "unknown")), str(report.get("model", job.get("model", "unknown"))))
            totals = by_model[key]
            totals["runs"] += 1
            totals["verified"] += report.get("status") == "verified_candidate"
            totals["tokens"] += report.get("estimated_tokens", 0)
            totals["reported"] += report.get("provider_input_tokens", 0) + report.get("provider_output_tokens", 0)

        def label(value):
            return value[:200].replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

        for suffix, field in (("runs", "runs"), ("verified", "verified"), ("tokens_estimated", "tokens"), ("tokens_reported", "reported")):
            name = "harness_model_" + suffix + "_total"
            lines.extend(["# HELP " + name + " Completed reports grouped by configured model.", "# TYPE " + name + " counter"])
            for (mode, provider, model), totals in sorted(by_model.items()):
                lines.append('%s{mode="%s",provider="%s",model="%s"} %s' % (name, label(mode), label(provider), label(model), totals[field]))
        if include_active:
            lines.extend(["# HELP harness_active_runs Currently executing runs.", "# TYPE harness_active_runs gauge", "harness_active_runs " + str(int(self.active is not None))])
        return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, status, body, content_type="application/json"):
        data = json.dumps(body).encode() if content_type == "application/json" else body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def valid_host(self):
        return self.headers.get("Host") in {"127.0.0.1:" + str(self.server.server_port), "localhost:" + str(self.server.server_port)}

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {"error": "Loopback host required"})
        path = urlparse(self.path).path
        store = self.server.store
        try:
            if path == "/api/config":
                return self.send(200, store.public_config())
            if path == "/api/runs":
                return self.send(200, {"runs": store.summaries(), "active": store.active})
            if path.startswith("/api/runs/"):
                bits = path.split("/")
                identity = bits[3]
                if len(bits) == 5 and bits[4] in {"patch", "report", "trace"}:
                    if identity not in store.jobs:
                        raise KeyError(identity)
                    name = {"patch": "candidate.patch", "report": "report.json", "trace": "trace.jsonl"}[bits[4]]
                    file = store.directory / identity / "result" / name
                    return self.send(200, file.read_bytes(), "text/plain; charset=utf-8")
                if len(bits) == 4:
                    return self.send(200, store.detail(identity))
            if path == "/metrics":
                return self.send(200, store.metrics(), "text/plain; version=0.0.4; charset=utf-8")
            if path in {"/", "/app.js", "/style.css", "/lucide.js"}:
                name = "index.html" if path == "/" else path[1:]
                mime = {"html": "text/html; charset=utf-8", "js": "text/javascript; charset=utf-8", "css": "text/css; charset=utf-8", "svg": "image/svg+xml"}[name.split(".")[-1]]
                return self.send(200, (STATIC / name).read_bytes(), mime)
            self.send(404, {"error": "Not found"})
        except (KeyError, FileNotFoundError):
            self.send(404, {"error": "Run or artifact not found"})

    def do_POST(self):
        store = self.server.store
        origin = self.headers.get("Origin")
        if not self.valid_host() or self.headers.get("X-Harness-Token") != store.csrf or (origin and origin != "http://" + self.headers.get("Host", "")):
            return self.send(403, {"error": "Same-origin session token required"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 64000:
                raise ValueError("Body must contain 1-64000 bytes")
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("JSON content type required")
            data = json.loads(self.rfile.read(length))
            path = urlparse(self.path).path
            if path == "/api/connection":
                return self.send(200, store.configure(data))
            if path == "/api/models":
                env = store.connection_env(data, listing=True)
                result = call_api(env["HARNESS_API_BASE"], env["HARNESS_API_KEY"], "/models")
                if not isinstance(result, dict) or not isinstance(result.get("data"), list):
                    raise ValueError("Provider did not return a compatible model list; enter the model ID manually")
                entries = result.get("data", [])
                models = sorted(item["id"] for item in entries if isinstance(item, dict) and isinstance(item.get("id"), str))
                return self.send(200, {"models": models})
            if path == "/api/runs":
                return self.send(202, {"id": store.start(data)})
            bits = path.split("/")
            if len(bits) == 5 and bits[1:3] == ["api", "runs"] and bits[4] == "cancel":
                store.cancel(bits[3])
                return self.send(200, {"status": "cancelling"})
            self.send(404, {"error": "Not found"})
        except (ValueError, TypeError, Stop, OSError) as exc:
            self.send(400, {"error": str(exc)})
        except KeyError:
            self.send(404, {"error": "Run not found"})


def main():
    parser = argparse.ArgumentParser(description="AI Harness local workspace")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data", default=".harness-data")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--adapter", type=json.loads, help="Trusted JSON command array")
    mode.add_argument("--provider", choices=list(KEYS))
    parser.add_argument("--model")
    parser.add_argument("--api-base")
    parser.add_argument("--api-key-env")
    args = parser.parse_args()
    adapter = args.adapter
    adapter_env = {}
    if adapter is not None and (not isinstance(adapter, list) or not adapter or not all(isinstance(a, str) and a for a in adapter)):
        parser.error("Adapter must be a nonempty JSON string array")
    if args.provider:
        try:
            adapter_env = configuration(args.provider, args.api_base, args.model or "", os.environ.get(args.api_key_env or KEYS[args.provider], ""))
            adapter = [sys.executable, str(Path(__file__).with_name("api_adapter.py"))]
        except ValueError as exc:
            parser.error(str(exc))
    elif adapter is None and os.environ.get("HARNESS_MODEL"):
        adapter = [sys.executable, str(Path(__file__).with_name("ollama_adapter.py"))]
    store = Store(args.data, adapter, adapter_env=adapter_env)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    server.store = store
    print("AI Harness: http://127.0.0.1:%d" % server.server_port, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if store.active:
            store.cancel(store.active)
        deadline = time.monotonic() + 5
        while store.active and time.monotonic() < deadline:
            time.sleep(.05)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
