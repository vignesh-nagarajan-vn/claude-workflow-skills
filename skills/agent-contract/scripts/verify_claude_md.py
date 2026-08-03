#!/usr/bin/env python3
"""Audit a CLAUDE.md for the four ways it rots: dead paths, dead commands, a stale
freshness date, and outgrowing its ceiling.

Stdlib only.

    python verify_claude_md.py
    python verify_claude_md.py --file docs/AGENTS.md --max-lines 150
    python verify_claude_md.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_FILE = "CLAUDE.md"
DEFAULT_MAX_LINES = 200

BACKTICK_RE = re.compile(r"`([^`\n]{2,120})`")
MDLINK_RE = re.compile(r"\]\(([^)\s]+)\)")
PATHISH_RE = re.compile(r"^[\w.@~-]+(?:/[\w.@ -]+)*/?$")
EXT_RE = re.compile(r"\.[A-Za-z0-9]{1,6}$")
NUMERIC_RE = re.compile(r"^[\d.]+$")

# Commands are only trusted inside code spans, because prose like
# "pnpm without a key" otherwise parses as a script name.
RUN_RE = re.compile(r"\b(?:npm|pnpm|yarn|bun)\s+run\s+([\w:.-]+)")
PNPM_DIRECT_RE = re.compile(r"\b(?:pnpm|yarn|bun)\s+([a-z][a-z0-9:_-]*)\b")
MAKE_RE = re.compile(r"\bmake\s+([a-z][\w:.-]*)")
DATE_RE = re.compile(r"last\s+(?:verified|updated|full update)\s*:?\s*\**\s*(\d{4}-\d{2}-\d{2})", re.I)

# Package-manager subcommands, not repo scripts.
PM_BUILTINS = {
    "install", "add", "remove", "up", "update", "dlx", "exec", "create", "init",
    "publish", "link", "why", "audit", "outdated", "store", "prune", "list",
    "test", "start", "run", "workspace", "config", "cache", "version", "pack",
}

KNOWN_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java",
    ".kt", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".scala",
    ".sh", ".ps1", ".bat", ".sql", ".css", ".scss", ".html", ".vue", ".svelte",
    ".lua", ".r", ".jl", ".tex", ".bib", ".md", ".rst", ".txt", ".json", ".yml",
    ".yaml", ".toml", ".ini", ".cfg", ".xml", ".lock", ".env", ".svg", ".png",
    ".jpg", ".jpeg", ".gif", ".webp", ".webm", ".mp4", ".pdf", ".csv", ".tsv",
    ".ipynb", ".proto", ".graphql", ".prisma", ".dockerfile", ".gitignore",
}
# Commonly gitignored, so absence is not rot.
IGNORE_NAMES = {".env", ".env.local", ".env.production", "node_modules", ".next", "dist", "build"}
PLACEHOLDER_HINTS = ("<", ">", "*", "{", "}", "...", "$", "|")
IGNORE_PREFIX = ("http://", "https://", "#", "mailto:", "tel:")


def _git(args: list[str]) -> str:
    try:
        r = subprocess.run(["git"] + args, capture_output=True, text=True, check=True)
        return r.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

def looks_like_path(text: str) -> bool:
    if not text or any(h in text for h in PLACEHOLDER_HINTS):
        return False
    if text.startswith(IGNORE_PREFIX) or text.startswith("@"):
        return False          # scoped package specifier, not a path
    if NUMERIC_RE.match(text):
        return False          # version or IP address
    if " " in text and "/" not in text:
        return False

    m = EXT_RE.search(text)
    if m:
        if m.group(0).lower() not in KNOWN_EXT:
            return False      # messages.create, page.route, 127.0.0.1
    elif not text.endswith("/"):
        return False          # next/font, application/x-ndjson, bg-x/10

    return bool(PATHISH_RE.match(text))


def extract(text: str) -> tuple[dict[str, int], dict[str, tuple[int, str]]]:
    """Return (path -> first line, command -> (line, kind))."""
    paths: dict[str, int] = {}
    commands: dict[str, tuple[int, str]] = {}

    def scan_commands(fragment: str, lineno: int) -> None:
        for m in RUN_RE.finditer(fragment):
            commands.setdefault(m.group(1), (lineno, "run"))
        for m in MAKE_RE.finditer(fragment):
            commands.setdefault(m.group(1), (lineno, "make"))
        for m in PNPM_DIRECT_RE.finditer(fragment):
            name = m.group(1)
            if name not in PM_BUILTINS:
                commands.setdefault(name, (lineno, "direct"))

    in_fence = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue

        if in_fence:
            scan_commands(raw, lineno)
            continue

        for m in BACKTICK_RE.finditer(raw):
            span = m.group(1).strip()
            scan_commands(span, lineno)
            candidate = span.rstrip(".,;:")
            if looks_like_path(candidate):
                paths.setdefault(candidate, lineno)

        for m in MDLINK_RE.finditer(raw):
            target = m.group(1).split("#")[0].strip()
            if target and not target.startswith(IGNORE_PREFIX):
                paths.setdefault(target, lineno)

    return paths, commands


def known_commands(root: Path) -> tuple[set[str], bool]:
    found: set[str] = set()
    saw_source = False

    for pkg in [root / "package.json"] + sorted(root.glob("*/package.json"))[:6]:
        if pkg.is_file():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
                found.update((data.get("scripts") or {}).keys())
                saw_source = True
            except (OSError, ValueError):
                pass

    mk = root / "Makefile"
    if mk.is_file():
        saw_source = True
        try:
            for line in mk.read_text(encoding="utf-8", errors="ignore").splitlines():
                m = re.match(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", line)
                if m:
                    found.add(m.group(1))
        except OSError:
            pass

    return found, saw_source


def tracked(root: Path) -> tuple[set[str], set[str], set[str]]:
    """Return (full relative paths, file basenames, directory names)."""
    out = _git(["ls-files"])
    full = {p.strip() for p in out.splitlines() if p.strip()}
    files = {Path(p).name for p in full}
    dirs: set[str] = set()
    for p in full:
        parts = Path(p).parts[:-1]
        dirs.update(parts)
    return full, files, dirs


# --------------------------------------------------------------------------
# Audit
# --------------------------------------------------------------------------

def audit(path: Path, root: Path, max_lines: int) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    paths, commands = extract(text)
    full, basenames, dirnames = tracked(root)

    base = path.parent
    dead_paths, shorthand = [], []
    for ref, lineno in sorted(paths.items(), key=lambda kv: kv[1]):
        stem = ref.rstrip("/")
        name = Path(stem).name
        if name in IGNORE_NAMES or stem in IGNORE_NAMES:
            continue
        if (base / ref).exists() or (root / ref).exists() or stem in full:
            continue
        # A leading-dot token with no slash is a suffix pattern (.md, .test.ts),
        # not a path. Real dotfiles resolve above.
        if ref.startswith(".") and "/" not in ref:
            continue
        if name in basenames or name in dirnames:
            shorthand.append({"ref": ref, "line": lineno})
            continue
        dead_paths.append({"ref": ref, "line": lineno})

    declared, saw_source = known_commands(root)
    dead_commands = []
    if saw_source:
        for name, (lineno, kind) in sorted(commands.items(), key=lambda kv: kv[1][0]):
            if name not in declared:
                dead_commands.append({"command": name, "line": lineno, "kind": kind})

    stamp = DATE_RE.search(text)
    freshness: dict = {"declared": stamp.group(1) if stamp else None}
    if stamp:
        last_commit = _git(["log", "-1", "--format=%cs"])
        freshness["last_commit"] = last_commit or None
        if last_commit:
            try:
                d0 = datetime.strptime(stamp.group(1), "%Y-%m-%d").date()
                d1 = datetime.strptime(last_commit, "%Y-%m-%d").date()
                freshness["drift_days"] = (d1 - d0).days
                since = _git(["rev-list", "--count", f"--since={stamp.group(1)}", "HEAD"])
                freshness["commits_since"] = int(since) if since.isdigit() else None
            except ValueError:
                pass

    return {
        "file": path.as_posix(),
        "lines": len(lines),
        "max_lines": max_lines,
        "refs_checked": len(paths),
        "dead_paths": dead_paths,
        "shorthand_paths": shorthand,
        "commands_checked": len(commands),
        "dead_commands": dead_commands,
        "freshness": freshness,
    }


def render(a: dict) -> str:
    out = [f"{a['file']}: {a['lines']} lines, {a['refs_checked']} path ref(s), "
           f"{a['commands_checked']} command(s)"]

    if a["dead_paths"]:
        out.append("")
        out.append(f"dead path references ({len(a['dead_paths'])}):")
        width = max(len(d["ref"]) for d in a["dead_paths"]) + 2
        for d in a["dead_paths"]:
            out.append(f"  {d['ref']:<{width}} line {d['line']}")

    if a["dead_commands"]:
        out.append("")
        out.append(f"commands not declared anywhere ({len(a['dead_commands'])}):")
        for d in a["dead_commands"]:
            out.append(f"  {d['command']:<24} line {d['line']}  ({d['kind']})")

    if a["shorthand_paths"]:
        out.append("")
        out.append(f"{len(a['shorthand_paths'])} reference(s) matched by filename only, "
                   "not by full path (shorthand, usually fine)")

    f = a["freshness"]
    out.append("")
    if not f.get("declared"):
        out.append("freshness: no 'Last verified' date, add one to the header")
    else:
        line = f"freshness: declared {f['declared']}"
        if f.get("last_commit"):
            line += f", last commit {f['last_commit']}"
        if f.get("commits_since") is not None:
            line += f", {f['commits_since']} commit(s) since"
        out.append(line)
        if (f.get("drift_days") or 0) > 30 or (f.get("commits_since") or 0) > 25:
            out.append("  -> drifted far enough to re-verify the claims")

    if a["lines"] > a["max_lines"]:
        out.append("")
        out.append(f"size: {a['lines']} lines is over the {a['max_lines']} ceiling, "
                   "move a section into docs/ and leave a pointer")

    if not a["dead_paths"] and not a["dead_commands"]:
        out.append("")
        out.append("no dead references or commands")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit a CLAUDE.md for rot.")
    parser.add_argument("--file", default=DEFAULT_FILE, help=f"default: {DEFAULT_FILE}")
    parser.add_argument("--max-lines", type=int, default=DEFAULT_MAX_LINES)
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(_git(["rev-parse", "--show-toplevel"]) or Path.cwd())
    path = Path(args.file)
    if not path.is_file():
        path = root / args.file
    if not path.is_file():
        print(f"no such file: {args.file}", file=sys.stderr)
        return 2

    result = audit(path, root, args.max_lines)
    print(json.dumps(result, indent=2) if args.as_json else render(result))
    return 1 if (result["dead_paths"] or result["dead_commands"]) else 0


if __name__ == "__main__":
    sys.exit(main())
