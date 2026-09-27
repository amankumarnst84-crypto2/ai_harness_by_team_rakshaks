"""Bounded lexical retrieval with Python AST symbols and line-addressed reads."""
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

from .safety import Stop, git, safe_path

STOP_WORDS = {"the", "and", "for", "from", "with", "that", "this", "must", "should", "when", "then", "than", "into", "before", "after", "while", "are", "was", "not", "but", "has", "have", "fix", "is", "in", "to", "as", "of", "on", "be", "an", "by", "at", "or", "it"}
STOP_WORDS.update({"py", "js", "ts", "tsx", "jsx", "rs", "go", "java", "cpp", "json", "toml", "md", "txt", "file", "line", "traceback", "most", "recent", "call", "last"})
MAX_FILE_BYTES = 2_000_000
MAX_INDEX_BYTES = 32_000_000
EXCLUDED_DIRS = {"node_modules", "vendor", "dist", "build", "venv", "__pycache__"}


def estimate(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return (len(text.encode("utf-8")) + 3) // 4


def words(text):
    return re.findall(r"[a-z_][a-z_0-9]{1,}", text.lower())


class Index:
    def __init__(self, root):
        self.root = root
        self.cache = {}
        self.cache_hits = 0
        self.skipped = 0
        self.skipped_bytes = 0

    def refresh(self):
        files = []
        total = 0
        self.skipped = 0
        self.skipped_bytes = 0
        names = []
        try:
            names = sorted(git(self.root, "ls-files", "-z").split("\0"))
        except Stop:
            raise Stop("Retrieval requires a Git repository; untracked files are never uploaded") from None
        for name in names[:10000]:
            if not name:
                continue
            try:
                if any(part in EXCLUDED_DIRS for part in Path(name).parts):
                    raise Stop("Generated dependency directory")
                path = safe_path(self.root, name)
                stat = path.stat()
                if not path.is_file() or stat.st_size > MAX_FILE_BYTES or total + stat.st_size > MAX_INDEX_BYTES:
                    self.skipped_bytes += stat.st_size
                    raise Stop("Large file")
                total += stat.st_size
                fingerprint = (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
                if name in self.cache and self.cache[name].get("fingerprint") == fingerprint:
                    files.append(self.cache[name])
                    self.cache_hits += 1
                    continue
                with path.open("rb") as stream:
                    raw = stream.read(MAX_FILE_BYTES + 1)
                if len(raw) > MAX_FILE_BYTES:
                    raise Stop("File grew past index limit")
                if b"\0" in raw:
                    raise Stop("Binary file")
                digest = hashlib.sha256(raw).hexdigest()
                if name in self.cache and self.cache[name]["sha256"] == digest:
                    record = self.cache[name]
                    self.cache_hits += 1
                else:
                    data = raw.decode("utf-8")
                    symbols = []
                    if name.endswith(".py"):
                        try:
                            tree = ast.parse(data)
                            symbols = [{"name": n.name, "line": n.lineno}
                                       for n in ast.walk(tree)
                                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
                        except (SyntaxError, ValueError, RecursionError):
                            pass
                    record = {"path": name, "content": data, "sha256": digest, "symbols": symbols,
                              "words": Counter(words(data)), "lines": data.splitlines(keepends=True)}
                    self.cache[name] = record
                record["fingerprint"] = fingerprint
                files.append(record)
            except (Stop, OSError, UnicodeError):
                self.skipped += 1
        self.files = files
        self.cache = {f["path"]: f for f in files}
        return self

    def select(self, query, char_budget=10000, reads=None):
        self.refresh()
        terms = set(words(query)) - STOP_WORDS
        counts = {f["path"]: f.get("words") if f.get("words") is not None else Counter(words(f["content"])) for f in self.files}
        df = Counter(t for t in terms for f in self.files if counts[f["path"]][t])
        average = sum(sum(c.values()) for c in counts.values()) / max(1, len(counts))

        def score(f):
            counter = counts[f["path"]]
            size = sum(counter.values())
            value = 0.0
            for term in terms:
                freq = counter[term]
                idf = math.log(1 + (len(self.files) - df[term] + .5) / (df[term] + .5))
                value += idf * freq * 2.2 / (freq + 1.2 * (.25 + .75 * size / max(1, average)))
                value += 5 * (term in set(words(str(Path(f["path"]).with_suffix("")))))
            value += 20 * (f["path"] in query)
            value += 12 * sum(s["name"].lower() in terms for s in f["symbols"])
            return value

        scores = {f["path"]: score(f) for f in self.files}
        ranked = sorted(self.files, key=lambda f: (-scores[f["path"]], f["path"]))
        selected = []
        used = 2
        seen = set()
        by_path = {f["path"]: f for f in self.files}

        def add(f, start, end):
            nonlocal used
            lines = f["lines"]
            start, end = max(1, start), min(len(lines), end)
            if start > end or (f["path"], start, end) in seen:
                return
            content = "".join(lines[start - 1:end])
            item = {"path": f["path"], "start_line": start, "end_line": end,
                    "sha256": f["sha256"][:16], "content": content,
                    "truncated": start > 1 or end < len(lines)}
            while len(json.dumps(item, ensure_ascii=False)) + used > char_budget and end > start:
                end -= 1
                item.update(end_line=end, content="".join(lines[start - 1:end]), truncated=True)
            cost = len(json.dumps(item, ensure_ascii=False)) + 2
            if used + cost <= char_budget:
                selected.append(item)
                seen.add((f["path"], start, end))
                used += cost

        for request in (reads or [])[:4]:
            if not isinstance(request, dict) or request.get("path") not in by_path:
                raise Stop("Requested read must target an indexed tracked file")
            start = request.get("start_line", 1)
            end = request.get("end_line", start + 79)
            if type(start) is not int or type(end) is not int or start < 1 or end < start or end - start > 199:
                raise Stop("Read ranges must contain 1-200 lines")
            add(by_path[request["path"]], start, end)
        for f in ranked:
            if scores[f["path"]] <= 0 and selected:
                break
            lines = f["lines"]
            if not lines:
                continue
            if len(lines) <= 70:
                add(f, 1, len(lines))
            else:
                matching = [s for s in f["symbols"] if s["name"].lower() in terms]
                for symbol in matching[:2]:
                    add(f, max(1, symbol["line"] - 1), symbol["line"] + 60)
                if matching:
                    continue
                windows = []
                for offset in range(0, len(lines), 40):
                    block = "".join(lines[offset:offset + 60])
                    frequencies = Counter(words(block))
                    relevance = sum(frequencies[t] for t in terms)
                    windows.append((-relevance, offset))
                for _, offset in sorted(windows)[:2]:
                    add(f, offset + 1, offset + 60)
            if used > char_budget - 250:
                break
        repo_map = []
        for f in ranked:
            row = f["path"] + " " + ", ".join(s["name"] + ":" + str(s["line"]) for s in f["symbols"][:5])
            if sum(len(r) + 1 for r in repo_map) + len(row) > 1600:
                break
            repo_map.append(row)
        full = sum(estimate({"path": f["path"], "content": f["content"]}) for f in self.files)
        packed = estimate({"files": selected, "repo_map": repo_map})
        return selected, repo_map, {"eligible_full_source_tokens_estimate": full,
                                   "selected_context_tokens_estimate": packed,
                                   "indexed_files": len(self.files), "skipped_files": self.skipped,
                                   "skipped_bytes": self.skipped_bytes,
                                   "index_cache_hits": self.cache_hits}


def compact_feedback(result, limit=3000):
    if result is None:
        return None
    answer = {k: v for k, v in result.items() if k not in {"stdout", "stderr"}}
    text = result.get("stderr", "") + "\n" + result.get("stdout", "")
    lines = list(dict.fromkeys(text.splitlines()))
    failure = [line for line in lines if re.search(r"(?i)(error|fail|assert|exception|\.\w+:\d+|File \"|expected|actual)", line)]
    focused = "\n".join(failure)[:limit // 2]
    tail = "\n".join(lines)[-(limit - len(focused)):]
    answer["output"] = focused + "\n" + tail
    answer["output_truncated"] = len(text) > limit
    return answer
