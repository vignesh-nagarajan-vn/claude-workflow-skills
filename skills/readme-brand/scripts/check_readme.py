#!/usr/bin/env python3
"""Check markdown links, images, and in-page anchors actually resolve.

Anchors are the ones nobody checks: a renamed heading silently breaks every
table-of-contents entry pointing at it, and nothing complains.

Stdlib only. Does not make network requests, so external URLs are counted and
skipped rather than fetched.

    python check_readme.py                # README.md
    python check_readme.py --all          # every tracked markdown file
    python check_readme.py docs/API.md
    python check_readme.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

LINK_RE = re.compile(r"(!?)\[(?P<text>[^\]]*)\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
HTML_IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")
HTML_ANCHOR_RE = re.compile(r"<a[^>]+(?:name|id)=[\"']([^\"']+)[\"']", re.I)
EXTERNAL = ("http://", "https://", "mailto:", "tel:", "//")

# Markdown that appears inside heading text and must be stripped before slugging.
INLINE_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
FORMAT_RE = re.compile(r"[*_`~]")
HTML_TAG_RE = re.compile(r"<[^>]+>")


def _git(args: list[str]) -> str:
    try:
        r = subprocess.run(["git"] + args, capture_output=True, text=True, check=True)
        return r.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def slugify(heading: str) -> str:
    """GitHub's heading-to-anchor rule, close enough for link checking."""
    text = INLINE_LINK_RE.sub(r"\1", heading)
    text = HTML_TAG_RE.sub("", text)
    text = FORMAT_RE.sub("", text)
    text = text.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    # Each whitespace character becomes its own hyphen, not one per run. Dropping
    # "&" from "Usage & Notes" leaves two spaces, so the real anchor is
    # "usage--notes". Collapsing the run here reports working links as broken.
    text = re.sub(r"\s", "-", text)
    return text.strip("-")


def collect_anchors(lines: list[str]) -> set[str]:
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    in_fence = False
    for raw in lines:
        stripped = raw.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = HEADING_RE.match(raw)
        if m:
            slug = slugify(m.group(2))
            if not slug:
                continue
            n = seen.get(slug, 0)
            anchors.add(slug if n == 0 else f"{slug}-{n}")
            seen[slug] = n + 1
        for a in HTML_ANCHOR_RE.finditer(raw):
            anchors.add(a.group(1))
    return anchors


def check(path: Path, root: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    anchors = collect_anchors(lines)
    base = path.parent

    broken_links, broken_anchors, missing_images = [], [], []
    external = 0
    n_links = n_images = 0

    in_fence = False
    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        targets: list[tuple[str, bool]] = []
        for m in LINK_RE.finditer(raw):
            targets.append((m.group("target"), m.group(1) == "!"))
        for m in HTML_IMG_RE.finditer(raw):
            targets.append((m.group(1), True))

        for target, is_image in targets:
            if is_image:
                n_images += 1
            else:
                n_links += 1

            if target.startswith(EXTERNAL):
                external += 1
                continue

            if target.startswith("#"):
                slug = target[1:]
                if slug and slug not in anchors:
                    broken_anchors.append({"target": target, "line": lineno})
                continue

            file_part = target.split("#")[0]
            if not file_part:
                continue
            candidate = (base / file_part)
            if candidate.exists() or (root / file_part).exists():
                # A link to another file with an anchor is not checked across files.
                continue
            entry = {"target": target, "line": lineno}
            (missing_images if is_image else broken_links).append(entry)

    try:
        display = path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        display = path.as_posix()

    return {
        "file": display,
        "links": n_links,
        "images": n_images,
        "external": external,
        "headings": len(anchors),
        "broken_links": broken_links,
        "broken_anchors": broken_anchors,
        "missing_images": missing_images,
    }


def render(results: list[dict]) -> str:
    out: list[str] = []
    total_problems = 0

    for r in results:
        problems = r["broken_links"] + r["broken_anchors"] + r["missing_images"]
        total_problems += len(problems)
        out.append(f"{r['file']}: {r['links']} link(s), {r['images']} image(s), "
                   f"{r['external']} external, {r['headings']} anchor(s)")

        for label, items in (("broken relative links", r["broken_links"]),
                             ("broken anchors", r["broken_anchors"]),
                             ("missing images", r["missing_images"])):
            if not items:
                continue
            out.append(f"  {label} ({len(items)}):")
            width = max(len(i["target"]) for i in items) + 2
            for i in items:
                note = "  (no matching heading)" if label == "broken anchors" else ""
                out.append(f"    {i['target']:<{width}} line {i['line']}{note}")
        out.append("")

    out.append("clean" if total_problems == 0 else f"{total_problems} problem(s)")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check markdown links, images, and anchors.")
    parser.add_argument("paths", nargs="*", help="default: README.md")
    parser.add_argument("--all", action="store_true", help="every tracked markdown file")
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(_git(["rev-parse", "--show-toplevel"]).strip() or Path.cwd())

    if args.all:
        names = [n for n in _git(["ls-files", "*.md"]).splitlines() if n.strip()]
        names += [n for n in _git(["ls-files", "--others", "--exclude-standard",
                                   "*.md"]).splitlines() if n.strip()]
        targets = [root / n for n in dict.fromkeys(names)]
    elif args.paths:
        targets = [Path(p) for p in args.paths]
    else:
        targets = [Path("README.md")]

    targets = [t for t in targets if t.is_file()]
    if not targets:
        print("no markdown files found", file=sys.stderr)
        return 2

    results = [check(t, root) for t in targets]
    print(json.dumps(results, indent=2) if args.as_json else render(results))

    problems = sum(len(r["broken_links"]) + len(r["broken_anchors"]) + len(r["missing_images"])
                   for r in results)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
