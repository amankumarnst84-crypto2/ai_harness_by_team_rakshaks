"""Build a source-only submission without local secrets, history or run artifacts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"Makefile", "requirements.txt", "README.md", "SUBMISSION.md", "ADAPTER.md",
              "COMPARISON.md", ".gitignore", ".env.example", "evaluate.py",
              "evaluation.example.json", "benchmark.py", "verify.py", "start.command", "LIVE_VALIDATION.md"}
SOURCE_DIRS = {"harness", "tests", "observability", "tools"}
SECRET = re.compile(r"(?:sk|gsk)[-_][A-Za-z0-9]{20,}")
EXCLUDED = {".git", ".venv", "__pycache__", ".harness-data", "dist", "build", "node_modules"}


def source_files(root=ROOT):
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not (Path(directory) / d).is_symlink())
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(root)
            if path.is_symlink() or path.suffix in {".pyc", ".png", ".zip"}:
                continue
            if name.startswith(".env") and relative.as_posix() != ".env.example":
                continue
            if relative.as_posix() in ROOT_FILES or relative.parts[0] in SOURCE_DIRS:
                yield path


def check(root=ROOT):
    errors = []
    for name in ("Makefile", "requirements.txt", "README.md", "SUBMISSION.md"):
        if not (root / name).is_file():
            errors.append("Missing " + name)
    if (root / "Makefile").is_file():
        makefile = (root / "Makefile").read_text()
        for target in ("setup", "run", "test", "clean"):
            if not re.search(r"^" + target + r":", makefile, re.M):
                errors.append("Missing Makefile target: " + target)
    files = list(source_files(root))
    for path in files:
        content = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(content.splitlines(), 1):
            if SECRET.search(line):
                errors.append(str(path.relative_to(root)) + ":" + str(number) + ": possible credential")
        if path.name == ".env.example":
            for line in content.splitlines():
                if line.startswith("AI_API_KEY=") and line.partition("=")[2].strip():
                    errors.append(".env.example must have an empty AI_API_KEY")
    if errors:
        raise ValueError("\n".join(errors))
    return files


def package(root=ROOT):
    files = check(root)
    destination = root / "dist"
    destination.mkdir(exist_ok=True)
    archive = destination / "rakshak-submission.zip"
    manifest = {}
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            name = path.relative_to(root).as_posix()
            data = path.read_bytes()
            manifest[name] = hashlib.sha256(data).hexdigest()
            info = zipfile.ZipInfo("rakshak/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if name == "start.command" else 0o644) << 16
            bundle.writestr(info, data)
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(str(archive))
    print(str(len(files)) + " source files; Git history, credentials, runs and big.js excluded.")
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "package", "clean"))
    action = parser.parse_args().action
    if action == "clean":
        for name in ("rakshak-submission.zip", "manifest.json"):
            (ROOT / "dist" / name).unlink(missing_ok=True)
        print("Generated archive removed. Run evidence and source preserved.")
    elif action == "package":
        package()
    else:
        print("Submission source check passed: " + str(len(check())) + " files. Not a full secret audit or benchmark.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc))
