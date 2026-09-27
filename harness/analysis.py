"""Bounded, non-executing source checks and a static local-import graph."""
import ast
import hashlib
import json
from pathlib import PurePosixPath
import posixpath
import re
import shutil

from .retrieval import Index
from .safety import Stop, command, protected_file

DEFAULT_ISSUE = "Inspect this repository for concrete bugs across related source files. Use the static diagnostics and local dependency graph. Propose minimal justified fixes, or return findings when a fix cannot be established. Do not change tests or claim runtime behavior was verified."
CODE_SUFFIXES = {".py", ".js", ".cjs", ".mjs", ".json", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".c", ".cpp", ".h", ".hpp"}
JS_IMPORT = re.compile(r'''(?:\b(?:import|export)\s+(?:[^;\n]*?\s+from\s+)?|\brequire\s*\(\s*)["'](\.[^"']+)["']''')
RUST_IMPORT = re.compile(r'''\b(?:use|mod)\s+([a-zA-Z0-9_:]+)''')
GO_IMPORT = re.compile(r'''\bimport\s+(?:\(\s*)?(?:[a-zA-Z0-9_]+\s+)?["']([^"']+)["']''')
JAVA_IMPORT = re.compile(r'''\bimport\s+([a-zA-Z0-9_.]+)''')
C_INCLUDE = re.compile(r'''#include\s+["<]([^">]+)[">]''')


def graph_for(files):
    names = {f["path"] for f in files}
    edges = set()

    def link(source, target):
        target = posixpath.normpath(target)
        for candidate in (target, target + ".py", target + "/__init__.py", target + ".js", target + ".ts", target + ".tsx", target + ".go", target + ".rs", target + ".java", target + ".c", target + ".cpp", target + ".h"):
            if candidate in names and candidate != source:
                edges.add((source, candidate))
                break

    for f in files:
        name = f["path"]
        parent = posixpath.dirname(name)
        if name.endswith(".py"):
            try:
                tree = ast.parse(f["content"])
            except (SyntaxError, ValueError, RecursionError):
                continue
            for item in ast.walk(tree):
                if isinstance(item, ast.Import):
                    for alias in item.names:
                        link(name, alias.name.replace(".", "/"))
                elif isinstance(item, ast.ImportFrom):
                    prefix = parent
                    for _ in range(max(0, item.level - 1)):
                        prefix = posixpath.dirname(prefix)
                    module = (item.module or "").replace(".", "/")
                    target = posixpath.join(prefix, module) if item.level else module
                    link(name, target)
                    for alias in item.names:
                        link(name, posixpath.join(target, alias.name))
        elif PurePosixPath(name).suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
            for target in JS_IMPORT.findall(f["content"]):
                link(name, posixpath.join(parent, target))
        elif name.endswith(".go"):
            for target in GO_IMPORT.findall(f["content"]):
                link(name, posixpath.join(parent, target))
                link(name, target)
        elif name.endswith(".rs"):
            for target in RUST_IMPORT.findall(f["content"]):
                link(name, posixpath.join(parent, target.replace("::", "/")))
        elif name.endswith(".java"):
            for target in JAVA_IMPORT.findall(f["content"]):
                link(name, posixpath.join(parent, target.replace(".", "/")))
        elif PurePosixPath(name).suffix in {".c", ".cpp", ".h", ".hpp"}:
            for target in C_INCLUDE.findall(f["content"]):
                link(name, posixpath.join(parent, target))
    return [{"from": a, "to": b, "kind": "test_import" if protected_file(a) else "import"} for a, b in sorted(edges)]


def affected_paths(edges, changed):
    affected = set(changed)
    while True:
        expanded = affected | {e["from"] for e in edges if e["to"] in affected}
        if expanded == affected:
            return sorted(affected)
        affected = expanded


def scan(root, env, left, cancel=None, max_files=200):
    index = Index(root).refresh()
    supported = []
    diagnostics, skipped, hashes = [], [], {}
    node = shutil.which("node", path=env.get("PATH"))
    source_files = [f for f in index.files if PurePosixPath(f["path"]).suffix in CODE_SUFFIXES]
    for f in source_files[:max_files]:
        left()
        name, content = f["path"], f["content"]
        suffix = PurePosixPath(name).suffix
        hashes[name] = hashlib.sha256(content.encode()).hexdigest()
        try:
            if suffix == ".py":
                compile(content, name, "exec", dont_inherit=True)
            elif suffix == ".json":
                json.loads(content)
            elif suffix in {".js", ".cjs", ".mjs"}:
                if not node:
                    skipped.append({"path": name, "reason": "Node.js unavailable"})
                    continue
                result = command([node, "--check", str(root / name)], root, left(), env=env, limit=12000, cancel=cancel)
                if result["reason"] == "cancelled":
                    raise Stop("Run cancelled")
                if result["reason"]:
                    skipped.append({"path": name, "reason": result["reason"]})
                    continue
                if result["code"]:
                    diagnostics.append({"path": name, "kind": "syntax", "message": result["stderr"][-1500:]})
            else:
                skipped.append({"path": name, "reason": "No built-in checker for " + suffix})
                continue
            supported.append(name)
        except (SyntaxError, ValueError, RecursionError) as exc:
            supported.append(name)
            diagnostics.append({"path": name, "kind": "syntax", "line": getattr(exc, "lineno", None), "message": str(exc)[:1500]})
    skipped.extend({"path": f["path"], "reason": "File check limit"} for f in source_files[max_files:])
    edges = graph_for(source_files[:max_files])
    return {"kind": "static_analysis", "behavior_verified": False, "checked_files": supported,
            "diagnostics": diagnostics, "skipped": skipped, "index_skipped": index.skipped,
            "complete": bool(supported) and not skipped,
            "graph": edges, "hashes": hashes,
            "limitations": "Syntax checks cover eligible indexed files only, not excluded files. Local imports are inferred, not executed. Dynamic imports, runtime behavior and external dependencies are not verified."}


def compare(before, after):
    def keys(scan):
        return {(d["path"], d["kind"], d["message"]) for d in scan["diagnostics"]}
    changed = sorted(name for name in before["hashes"].keys() | after["hashes"].keys()
                     if before["hashes"].get(name) != after["hashes"].get(name))
    return {"changed_files": changed, "affected_files": affected_paths(before["graph"] + after["graph"], changed),
            "resolved_diagnostics": len(keys(before) - keys(after)),
            "introduced_diagnostics": len(keys(after) - keys(before)), "behavior_verified": False}


def summary(result):
    return {"kind": result["kind"], "behavior_verified": False, "complete": result["complete"],
            "checked_files": len(result["checked_files"]), "diagnostics": [{**d, "message": d["message"][:350]} for d in result["diagnostics"][:10]],
            "skipped_files": len(result["skipped"]) + result["index_skipped"],
            "local_dependencies": result["graph"][:30], "limitations": result["limitations"]}


def build_audit_request(issue, patch_diff, changed_files, downstream_files, graph, baseline_diff=None):
    """Constructs prompt for the Behavioral Intentionality Gate (comparing before vs after)."""
    edges = [e for e in graph if e["to"] in changed_files and e["from"] in downstream_files]
    dep_summary = ", ".join(f"{e['from']} imports {e['to']}" for e in edges[:10])
    
    instruction = (
        "You are a Behavioral Intentionality Gate auditing code changes against a dependency graph. "
        "A patch was applied to fix an issue, and downstream modules depend on the modified code. "
    )
    if baseline_diff:
        instruction += "Note that a healthy BASELINE exists. The regression from baseline to broken state is provided. "
    
    instruction += (
        "Determine whether this behavioral change is intentional and contract-compatible for callers, "
        "or if it introduces an unintended regression / breaking API change. If the patch restores the behavior to a known healthy baseline, it should be considered intentional.\n"
        "Return JSON: {\"intentional\": true|false, \"reason\": \"concise rationale\"}"
    )

    req = {
        "instruction": instruction,
        "issue": issue,
        "changed_files": changed_files,
        "affected_downstream_files": downstream_files,
        "dependency_relationships": dep_summary or "Direct callers/dependents identified in project graph",
        "patch_diff": patch_diff[:4000],
        "max_output_tokens": 300,
    }
    if baseline_diff:
        req["regression_from_baseline_diff"] = baseline_diff[:4000]
    return req


def parse_audit_response(raw):
    """Safely extracts intentionality decision from model audit output."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data, dict):
            intentional = bool(data.get("intentional", True))
            reason = str(data.get("reason", data.get("plan", "")))[:500]
            return intentional, reason
    except Exception:
        pass
    return True, "Defaulted to accept"
