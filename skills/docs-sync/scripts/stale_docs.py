#!/usr/bin/env python3
"""Report which docs a code change made stale, using .claude/docs-map.yml.

Stdlib only, no yaml dependency. Parses the restricted subset the template uses:
a quoted or bare glob key, then an indented list of doc paths.

    python stale_docs.py                  # uncommitted work vs HEAD
    python stale_docs.py --base main      # a whole branch
    python stale_docs.py --staged         # pre-commit hook
    python stale_docs.py --verify         # CI gate, nonzero if stale
    python stale_docs.py --init           # write a starter map
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_MAP = Path(".claude/docs-map.yml")
TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "docs-map.template.yml"

KEY_RE = re.compile(r'^(?P<key>"[^"]+"|\'[^\']+\'|[^\s#][^:]*?)\s*:\s*(?P<inline>.*)$')
ITEM_RE = re.compile(r"^\s*-\s+(?P<item>.+?)\s*$")


# --------------------------------------------------------------------------
# Map parsing
# --------------------------------------------------------------------------

def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _strip_comment(line: str) -> str:
    """Drop a trailing comment, but not a # inside quotes."""
    out = []
    quote = None
    for ch in line:
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            break
        out.append(ch)
    return "".join(out).rstrip()


def parse_map(path: Path) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    current: str | None = None
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = _strip_comment(raw)
        if not line.strip():
            continue

        item = ITEM_RE.match(line)
        if item and current is not None:
            mapping[current].append(_unquote(item.group("item")))
            continue

        key_match = KEY_RE.match(line)
        if key_match and not line.startswith((" ", "\t")):
            current = _unquote(key_match.group("key"))
            mapping.setdefault(current, [])
            inline = key_match.group("inline").strip()
            if inline.startswith("[") and inline.endswith("]"):
                for piece in inline[1:-1].split(","):
                    if piece.strip():
                        mapping[current].append(_unquote(piece))
            continue

        print(f"warning: {path}:{lineno}: could not parse: {raw.strip()}", file=sys.stderr)

    return {k: v for k, v in mapping.items() if v}


# --------------------------------------------------------------------------
# Globbing
# --------------------------------------------------------------------------

def glob_to_regex(pattern: str) -> re.Pattern:
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


# --------------------------------------------------------------------------
# Git
# --------------------------------------------------------------------------

def _git(args: list[str]) -> list[str]:
    try:
        result = subprocess.run(
            ["git"] + args, capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        print("error: git not found on PATH", file=sys.stderr)
        sys.exit(2)
    except subprocess.CalledProcessError as exc:
        print(f"error: git {' '.join(args)} failed: {exc.stderr.strip()}", file=sys.stderr)
        sys.exit(2)
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def changed_files(base: str | None, staged: bool) -> list[str]:
    if staged:
        return _git(["diff", "--name-only", "--cached"])
    if base:
        return _git(["diff", "--name-only", base])
    tracked = _git(["diff", "--name-only", "HEAD"])
    untracked = _git(["ls-files", "--others", "--exclude-standard"])
    return sorted(set(tracked) | set(untracked))


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

def find_stale(mapping: dict[str, list[str]], changed: list[str]) -> tuple[dict, dict]:
    """Return (stale, satisfied). Each maps doc -> list of (source, glob)."""
    changed_set = set(changed)
    triggers: dict[str, list[tuple[str, str]]] = {}

    for pattern, docs in mapping.items():
        regex = glob_to_regex(pattern)
        hits = [f for f in changed if regex.match(f)]
        if not hits:
            continue
        for doc in docs:
            for hit in hits:
                if hit == doc:
                    continue  # a doc triggering itself is noise
                triggers.setdefault(doc, []).append((hit, pattern))

    stale = {d: t for d, t in triggers.items() if d not in changed_set}
    satisfied = {d: t for d, t in triggers.items() if d in changed_set}
    return stale, satisfied


def report(stale: dict, satisfied: dict, changed: list[str], show_all: bool) -> None:
    if not changed:
        print("no changes detected")
        return

    if satisfied and show_all:
        print(f"already updated ({len(satisfied)}):")
        for doc in sorted(satisfied):
            print(f"  {doc}")
        print()

    if not stale:
        print(f"docs are in sync ({len(changed)} changed file(s))")
        return

    print(f"docs to review ({len(stale)}):")
    for doc in sorted(stale):
        exists = "" if Path(doc).exists() else "   [missing on disk]"
        print(f"  {doc}{exists}")
        seen = set()
        for source, pattern in stale[doc]:
            if source in seen:
                continue
            seen.add(source)
            print(f"      <- {source}  [{pattern}]")
            if len(seen) >= 4:
                remaining = len({s for s, _ in stale[doc]}) - 4
                if remaining > 0:
                    print(f"      <- ... and {remaining} more")
                break


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Find docs made stale by a code change.")
    parser.add_argument("--map", default=str(DEFAULT_MAP), help=f"map file (default: {DEFAULT_MAP})")
    parser.add_argument("--base", help="git ref to compare against, e.g. main")
    parser.add_argument("--staged", action="store_true", help="only staged changes")
    parser.add_argument("--verify", action="store_true", help="exit 1 if any mapped doc is stale")
    parser.add_argument("--all", action="store_true", help="also list docs already updated")
    parser.add_argument("--json", dest="as_json", action="store_true", help="emit JSON")
    parser.add_argument("--init", action="store_true", help="write a starter map and exit")
    args = parser.parse_args(argv)

    map_path = Path(args.map)

    if args.init:
        if map_path.exists():
            print(f"{map_path} already exists, not overwriting", file=sys.stderr)
            return 1
        if not TEMPLATE.exists():
            print(f"error: template missing at {TEMPLATE}", file=sys.stderr)
            return 2
        map_path.parent.mkdir(parents=True, exist_ok=True)
        map_path.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"wrote {map_path}; edit it against this repo, then commit it")
        return 0

    if not map_path.exists():
        print(f"no map at {map_path}", file=sys.stderr)
        print("run with --init to create one, or grep the changed identifiers "
              'across "*.md" instead', file=sys.stderr)
        return 2

    mapping = parse_map(map_path)
    if not mapping:
        print(f"error: {map_path} parsed to zero entries", file=sys.stderr)
        return 2

    changed = changed_files(args.base, args.staged)
    stale, satisfied = find_stale(mapping, changed)

    if args.as_json:
        print(json.dumps({
            "changed": changed,
            "stale": {d: [{"source": s, "glob": g} for s, g in t] for d, t in stale.items()},
            "satisfied": sorted(satisfied),
        }, indent=2))
    else:
        report(stale, satisfied, changed, args.all)

    return 1 if (args.verify and stale) else 0


if __name__ == "__main__":
    sys.exit(main())
