#!/usr/bin/env python3
"""Collect the mechanical facts for a HANDOFF.md so the model does not parse git output.

Stdlib only.

    python handoff_context.py                 # since the last handoff, else last 10 commits
    python handoff_context.py --since main
    python handoff_context.py --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

HANDOFF = "HANDOFF.md"
MAX_FILES = 25
MAX_COMMITS = 15


def _git(args: list[str], allow_fail: bool = False) -> str:
    try:
        result = subprocess.run(["git"] + args, capture_output=True, text=True, check=not allow_fail)
    except FileNotFoundError:
        print("error: git not found on PATH", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as exc:
        if allow_fail:
            return ""
        print(f"error: git {' '.join(args)} failed: {exc.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return result.stdout.strip()


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def default_since() -> tuple[str, str]:
    """Prefer the last commit that touched HANDOFF.md, else fall back to HEAD~10."""
    if Path(HANDOFF).exists():
        sha = _git(["log", "-1", "--format=%H", "--", HANDOFF], allow_fail=True)
        if sha:
            return sha, f"last {HANDOFF} commit"
    total = _git(["rev-list", "--count", "HEAD"], allow_fail=True)
    try:
        depth = min(10, max(int(total) - 1, 0))
    except ValueError:
        depth = 0
    if depth == 0:
        return "", "repo start"
    return f"HEAD~{depth}", f"last {depth} commit" + ("s" if depth != 1 else "")


def collect(since: str | None) -> dict:
    if not _git(["rev-parse", "--is-inside-work-tree"], allow_fail=True):
        print("error: not inside a git work tree", file=sys.stderr)
        sys.exit(2)

    if since:
        base, base_label = since, since
    else:
        base, base_label = default_since()

    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], allow_fail=True) or "(detached)"
    sha = _git(["rev-parse", "--short", "HEAD"], allow_fail=True) or "(none)"

    dirty = _lines(_git(["status", "--porcelain"], allow_fail=True))
    staged = _lines(_git(["diff", "--name-only", "--cached"], allow_fail=True))

    rev_range = f"{base}..HEAD" if base else "HEAD"
    commits = _lines(_git(["log", rev_range, "--format=%h %s"], allow_fail=True))
    files = _lines(_git(["diff", "--name-only", base], allow_fail=True)) if base else []
    if not files:
        files = _lines(_git(["diff", "--name-only", "HEAD"], allow_fail=True))

    untracked = [ln[3:] for ln in dirty if ln.startswith("??")]

    return {
        "date": date.today().isoformat(),
        "branch": branch,
        "sha": sha,
        "base": base,
        "base_label": base_label,
        "dirty_count": len(dirty),
        "staged_count": len(staged),
        "untracked": untracked,
        "commits": commits,
        "files": sorted(set(files)),
    }


def render(info: dict) -> str:
    out: list[str] = []
    # ASCII separators: this goes to a console, and Windows code pages mangle punctuation.
    out.append(f"**Date:** {info['date']} | **Branch:** `{info['branch']}` @ `{info['sha']}` "
               f"| **Uncommitted:** {info['dirty_count']} file(s)")
    out.append("")

    commits = info["commits"]
    out.append(f"Commits since {info['base_label']} ({len(commits)}):")
    if commits:
        for line in commits[:MAX_COMMITS]:
            out.append(f"  {line}")
        if len(commits) > MAX_COMMITS:
            out.append(f"  ... and {len(commits) - MAX_COMMITS} more")
    else:
        out.append("  (none)")
    out.append("")

    files = info["files"]
    out.append(f"Files touched ({len(files)}):")
    if files:
        for path in files[:MAX_FILES]:
            out.append(f"  {path}")
        if len(files) > MAX_FILES:
            out.append(f"  ... and {len(files) - MAX_FILES} more")
    else:
        out.append("  (none)")

    if info["untracked"]:
        out.append("")
        out.append(f"Untracked ({len(info['untracked'])}): " + ", ".join(info["untracked"][:10]))

    out.append("")
    out.append("Now write the parts git cannot answer: where things stand, what is in "
               "flight and in which file, what is next, and the gotchas.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gather facts for a handoff file.")
    parser.add_argument("--since", help="git ref to summarize from, e.g. main")
    parser.add_argument("--json", dest="as_json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    info = collect(args.since)
    print(json.dumps(info, indent=2) if args.as_json else render(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
