"""Local process and edit boundaries. A checkout is not an OS sandbox."""
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time


class Stop(Exception):
    pass


class EditError(Stop):
    def __init__(self, message, path, line=1):
        super().__init__(message)
        self.path, self.line = path, line


def command(argv, cwd, timeout, env=None, limit=2000000, cancel=None):
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(argv, cwd=str(cwd), env=env, stdout=out,
                                stderr=err, start_new_session=True)
        deadline = time.monotonic() + timeout
        reason = None
        try:
            while proc.poll() is None:
                if cancel is not None and cancel.is_set():
                    reason = "cancelled"
                elif time.monotonic() >= deadline:
                    reason = "timeout"
                elif os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > limit:
                    reason = "output_limit"
                if reason:
                    break
                time.sleep(0.02)
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
        out.seek(0)
        err.seek(0)
        stdout = out.read(limit)
        stderr = err.read(max(0, limit - len(stdout)))
        if os.fstat(out.fileno()).st_size + os.fstat(err.fileno()).st_size > limit and not reason:
            reason = "output_limit"
        return {"code": proc.returncode, "reason": reason,
                "stdout": stdout.decode("utf-8", "replace"),
                "stderr": stderr.decode("utf-8", "replace")}


def git(root, *args):
    result = command(["git", "-c", "core.hooksPath=/dev/null", *args], root, 15)
    if result["code"] or result["reason"]:
        raise Stop("Git operation failed: " + args[0])
    return result["stdout"]


def safe_path(root, name):
    if not isinstance(name, str):
        raise Stop("Path must be a string")
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise Stop("Unsafe path")
    if any(part.startswith(".") for part in path.parts):
        raise Stop("Hidden paths are excluded")
    if re.search(r"(?i)(secret|credential|password|\.pem$|\.key$|\.env)", name):
        raise Stop("Sensitive path excluded")
    dest = root / path
    if any((root / Path(*path.parts[:i])).is_symlink() for i in range(1, len(path.parts) + 1)):
        raise Stop("Symlink paths are excluded")
    if root.resolve() not in dest.resolve().parents:
        raise Stop("Path outside checkout")
    return dest


def protected_file(name, test_command=()):
    path = Path(name)
    stem = path.stem.lower()
    is_test = (any(p.lower() in {"test", "tests", "__tests__", "spec", "specs"} for p in path.parts)
               or stem.startswith("test") or stem.endswith(("_test", "test", "tests", "spec"))
               or ".test." in name.lower() or ".spec." in name.lower()
               or "check" in stem or "verify" in stem)
    is_config = path.name in {"conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini",
                              "package.json", "Makefile", "Cargo.toml", "go.mod"}
    is_test_arg = any(str(arg).removeprefix("./") == name and (is_test or "test" in str(arg).lower() or "check" in str(arg).lower())
                      for arg in (test_command or ()))
    return is_test or is_config or is_test_arg


def strip_fences(text):
    s = text.strip()
    if s.startswith("```") and s.endswith("```"):
        lines = s.splitlines()
        if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
            return "\n".join(lines[1:-1])
    return text


def find_and_replace_tolerant(data, old, new):
    if old == new:
        return data
    if data.count(old) == 1:
        return data.replace(old, new, 1)

    old_clean = strip_fences(old)
    new_clean = strip_fences(new)
    if data.count(old_clean) == 1:
        return data.replace(old_clean, new_clean, 1)

    data_norm = data.replace("\r\n", "\n")
    old_norm = old_clean.replace("\r\n", "\n")
    new_norm = new_clean.replace("\r\n", "\n")
    if data_norm.count(old_norm) == 1:
        replaced = data_norm.replace(old_norm, new_norm, 1)
        return replaced if "\r\n" not in data else replaced.replace("\n", "\r\n")

    old_lines = old_norm.splitlines()
    data_lines = data_norm.splitlines()
    if old_lines and len(data_lines) >= len(old_lines):
        k = len(old_lines)
        matches = []
        for i in range(len(data_lines) - k + 1):
            window = data_lines[i : i + k]
            if all(w.strip() == o.strip() for w, o in zip(window, old_lines)):
                deltas = [
                    len(w) - len(w.lstrip()) - (len(o) - len(o.lstrip()))
                    for w, o in zip(window, old_lines)
                    if w.strip() and o.strip()
                ]
                if deltas and len(set(deltas)) == 1:
                    matches.append((i, deltas[0]))

        if len(matches) == 1:
            idx, delta = matches[0]
            new_lines = new_norm.splitlines()
            adjusted_new = []
            for n_line in new_lines:
                if not n_line.strip():
                    adjusted_new.append("")
                elif delta > 0:
                    adjusted_new.append(" " * delta + n_line)
                elif delta < 0:
                    to_remove = min(-delta, len(n_line) - len(n_line.lstrip()))
                    adjusted_new.append(n_line[to_remove:])
                else:
                    adjusted_new.append(n_line)
            res_lines = data_lines[:idx] + adjusted_new + data_lines[idx + k :]
            result = "\n".join(res_lines)
            if data_norm.endswith("\n"):
                result += "\n"
            return result if "\r\n" not in data else result.replace("\n", "\r\n")

    return None


def edit(root, edits, test_command=()):
    if not isinstance(edits, list) or not edits or len(edits) > 20:
        raise Stop("Expected between 1 and 20 edits")
    tracked = set(git(root, "ls-files", "-z").split("\0"))
    staged = {}
    original = {}
    for item in edits:
        if not isinstance(item, dict):
            raise Stop("Each edit must be an object")
        name = item["path"]
        path = safe_path(root, name)
        if name not in tracked:
            raise Stop("Edits must target tracked files")
        if protected_file(name, test_command):
            raise Stop("Tests and test configuration are read-only: " + name)
        if path.stat().st_size > 200000:
            raise Stop("Edited file too large")
        data = staged[path] if path in staged else path.read_text()
        original.setdefault(path, data)
        old, new = item["old"], item["new"]
        if not isinstance(old, str) or not isinstance(new, str):
            raise Stop("Each edit must contain old and new string fields")
        if not old and data:
            raise EditError("Edit requires nonempty old text for replacement unless the file is entirely empty", name)
        if old == new:
            continue
        replaced = find_and_replace_tolerant(data, old, new)
        if replaced is None:
            raise EditError("Edit requires exactly one matching old string; copy it from current source", name)
        staged[path] = replaced
        if len(staged[path].encode()) > 200000:
            raise Stop("Edited file too large")
    # Validate the whole batch before writing any file, preserving the last candidate.
    for path, data in staged.items():
        if path.suffix == ".py":
            try:
                compile(data, str(path.relative_to(root)), "exec", dont_inherit=True)
            except (SyntaxError, ValueError) as exc:
                line = getattr(exc, "lineno", None)
                detail = getattr(exc, "msg", str(exc))
                raise EditError("Python syntax rejected in {} at line {}: {}. "
                           "No edits applied; retry against the unchanged source.".format(
                               path.relative_to(root), line or "unknown", detail),
                                str(path.relative_to(root)), line or 1) from None
    if not any(data != original[path] for path, data in staged.items()):
        raise EditError("Edit makes no change; propose a different, minimal replacement", edits[0]["path"])
    for path, data in staged.items():
        path.write_text(data)


def redact(text):
    pattern = r'''(?i)((?:["']?)(?:api[_-]?key|access[_-]?token|password|secret)(?:["']?)\s*[:=]\s*)("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[^\s,;}]+)'''
    def mask(match):
        value = match[2]
        quote = value[0] if value[0] in "\"'" else ""
        return match[1] + quote + "[REDACTED]" + quote
    text = re.sub(pattern, mask, text)
    for key, value in os.environ.items():
        if re.search(r"(?i)(key|token|secret|password)", key) and len(value) >= 6:
            text = text.replace(value, "[REDACTED]")
    return text


def clean(value, sensitive=()):
    if isinstance(value, str):
        value = redact(value)
        for secret in sensitive:
            if secret:
                value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, dict):
        return {k: "[REDACTED]" if re.fullmatch(r"(?i)(api[_-]?key|access[_-]?token|password|secret)", str(k))
                else clean(v, sensitive) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v, sensitive) for v in value]
    return value
