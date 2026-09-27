"""Intake module: turn Git URLs, GitHub issue links, local directories, or file paths
into a verified local Git repository and structured issue prompt.
Zero external dependencies: uses standard library urllib.request and git.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from .safety import Stop, command, git

ISSUE_URL_RE = re.compile(
    r"https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/(?:issues|pull)/(?P<num>\d+)"
)
GIT_URL_RE = re.compile(
    r"^(?:https?://|git@|ssh://|git://)[^\s]+(?:\.git)?$"
)
GITHUB_REPO_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git|/)?$"
)


def is_git_url(text: str) -> bool:
    if not isinstance(text, str):
        return False
    text = text.strip()
    return bool(GIT_URL_RE.match(text) or GITHUB_REPO_URL_RE.match(text))


def is_github_issue_url(text: str) -> bool:
    if not isinstance(text, str):
        return False
    return bool(ISSUE_URL_RE.search(text.strip()))


def parse_github_url(url: str) -> dict | None:
    text = url.strip()
    m_issue = ISSUE_URL_RE.search(text)
    if m_issue:
        return {
            "type": "issue",
            "owner": m_issue.group("owner"),
            "repo": m_issue.group("repo"),
            "num": m_issue.group("num"),
            "repo_url": f"https://github.com/{m_issue.group('owner')}/{m_issue.group('repo')}.git",
        }
    m_repo = GITHUB_REPO_URL_RE.match(text)
    if m_repo:
        return {
            "type": "repo",
            "owner": m_repo.group("owner"),
            "repo": m_repo.group("repo"),
            "num": None,
            "repo_url": f"https://github.com/{m_repo.group('owner')}/{m_repo.group('repo')}.git",
        }
    return None


def fetch_github_issue(url: str, max_comments: int = 5) -> dict:
    """Fetch GitHub issue title, body, and comments via REST API -> gh CLI -> raw HTML.
    Returns: {"title": str, "body": str, "repo_url": str, "full_text": str}
    """
    m = ISSUE_URL_RE.search(url.strip())
    if not m:
        raise ValueError(f"Not a valid GitHub issue or pull request URL: {url}")
    owner, repo, num = m.group("owner"), m.group("repo"), m.group("num")
    repo_url = f"https://github.com/{owner}/{repo}.git"

    # 1. Try GitHub REST API
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{num}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "RAKSHAK-AI-Harness/2",
    }
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        headers["Authorization"] = f"Bearer {tok}"

    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
            title = data.get("title", "")
            body = data.get("body") or ""
            full_text = f"[{owner}/{repo}#{num}] {title}\n\n{body}".strip()
            return {
                "title": title,
                "body": body,
                "repo_url": repo_url,
                "full_text": full_text,
            }
    except Exception:
        pass

    # 2. Try `gh` CLI if installed
    if shutil.which("gh"):
        try:
            res = subprocess.run(
                ["gh", "issue", "view", num, "-R", f"{owner}/{repo}", "--json", "title,body"],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if res.returncode == 0:
                data = json.loads(res.stdout)
                title = data.get("title", "")
                body = data.get("body") or ""
                full_text = f"[{owner}/{repo}#{num}] {title}\n\n{body}".strip()
                return {
                    "title": title,
                    "body": body,
                    "repo_url": repo_url,
                    "full_text": full_text,
                }
        except Exception:
            pass

    # 3. Fallback: fetch HTML page and scrape title/description
    html_url = f"https://github.com/{owner}/{repo}/issues/{num}"
    try:
        req = urllib.request.Request(
            html_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", "replace")
            title_match = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
            title = title_match.group(1).split("·")[0].strip() if title_match else f"{owner}/{repo}#{num}"
            desc_match = re.search(r'<meta property="og:description" content="(.*?)"', html, re.I | re.S)
            body = desc_match.group(1).strip() if desc_match else ""
            full_text = f"[{owner}/{repo}#{num}] {title}\n\n{body}".strip()
            return {
                "title": title,
                "body": body,
                "repo_url": repo_url,
                "full_text": full_text,
            }
    except Exception:
        pass

    # Basic fallback if offline or unreachable
    fallback_text = f"[{owner}/{repo}#{num}] Issue URL: {url}"
    return {
        "title": f"Issue #{num}",
        "body": url,
        "repo_url": repo_url,
        "full_text": fallback_text,
    }


def resolve_repo(repo_input: str, data_dir: Path | None = None) -> Path:
    """Resolve a repository input string to a local, clean Git repository Path.
    Handles:
      - Local Git repository directory
      - Local non-Git directory (initializes git baseline automatically)
      - Git remote URL (https://..., git@...) -> clones to data_dir/clones/
      - GitHub Issue URL -> extracts repo URL and clones it
    """
    if not repo_input or not isinstance(repo_input, str):
        raise Stop("Repository path or URL is required")
    repo_input = repo_input.strip()

    # Case A: GitHub Issue URL passed into repository input
    if is_github_issue_url(repo_input):
        info = parse_github_url(repo_input)
        if info and info.get("repo_url"):
            repo_input = info["repo_url"]

    # Case B: Remote Git URL
    if is_git_url(repo_input):
        if data_dir is None:
            data_dir = Path.home() / ".local" / "share" / "rakshak"
        clones_dir = Path(data_dir) / "clones"
        clones_dir.mkdir(parents=True, exist_ok=True)

        # Build clean clone directory name
        slug = re.sub(r"[^\w.-]+", "_", repo_input.split("/")[-1].removesuffix(".git"))
        target = clones_dir / slug
        if not (target / ".git").exists():
            # Clone cleanly
            res = subprocess.run(
                ["git", "clone", "--depth", "50", repo_input, str(target)],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if res.returncode != 0:
                raise Stop(f"Failed to clone repository {repo_input}: {res.stderr.strip()}")
        else:
            # If already cloned and clean, fetch latest
            try:
                if not git(target, "status", "--porcelain").strip():
                    git(target, "fetch", "--depth=50")
            except Exception:
                pass
        return target.resolve()

    # Case C: Local filesystem path
    local_path = Path(repo_input).expanduser().resolve()
    if not local_path.exists():
        raise Stop(f"Specified repository path does not exist: {local_path}")
    if not local_path.is_dir():
        raise Stop(f"Specified repository path is not a directory: {local_path}")

    # Check if local_path is a Git repository
    git_dir = local_path / ".git"
    if not git_dir.exists():
        # Auto-initialize a git repository baseline so Rakshak can run isolated git checkouts!
        try:
            subprocess.run(["git", "init", "-q"], cwd=local_path, check=True)
            subprocess.run(["git", "add", "-A"], cwd=local_path, check=True)
            subprocess.run(
                ["git", "-c", "user.name=rakshak", "-c", "user.email=rakshak@localhost", "commit", "-q", "-m", "baseline"],
                cwd=local_path,
                check=True,
            )
        except Exception as exc:
            raise Stop(f"Directory is not a Git repository and could not be initialized: {exc}")

    # Ensure it's the repo root
    try:
        toplevel = Path(git(local_path, "rev-parse", "--show-toplevel").strip()).resolve()
        if toplevel != local_path:
            return toplevel
    except Stop:
        pass

    return local_path


def resolve_issue(issue_input: str, repo_input: str = "") -> str:
    """Resolve issue input:
      - If issue_input is a GitHub issue URL, fetch title and body.
      - If issue_input starts with '@' (e.g. @task.md), read the local file.
      - If issue_input is empty but repo_input is an issue URL, fetch issue from repo_input.
      - Otherwise, return cleaned issue text.
    """
    issue_text = (issue_input or "").strip()

    # If issue text is a GitHub issue URL
    if is_github_issue_url(issue_text):
        fetched = fetch_github_issue(issue_text)
        return fetched.get("full_text") or issue_text

    # If issue is empty but repository input had an issue URL
    if not issue_text and repo_input and is_github_issue_url(repo_input.strip()):
        fetched = fetch_github_issue(repo_input.strip())
        return fetched.get("full_text") or repo_input.strip()

    # If issue references a local file e.g. @prompt.md
    if issue_text.startswith("@") and len(issue_text) > 1:
        file_path = Path(issue_text[1:]).expanduser().resolve()
        if file_path.is_file():
            return file_path.read_text(errors="replace").strip()

    return issue_text
