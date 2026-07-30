#!/usr/bin/env python3
"""Detect em dashes, AI-tell vocabulary, hedge stacking, and bullet bloat in prose.

Stdlib only. Run with no arguments to lint every git-tracked Markdown file.

    python prose_lint.py                     # whole repo
    python prose_lint.py README.md docs/     # specific paths
    python prose_lint.py --fail-on medium    # strict
    python prose_lint.py --fix               # rewrite unambiguous em dashes
    python prose_lint.py --stats             # counts by rule
    python prose_lint.py --json              # machine readable
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SEVERITIES = ("low", "medium", "high")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}

# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------
# (rule_id, severity, pattern, message)

TELLS_HIGH = [
    ("delve", r"\bdelv(?:e|es|ed|ing)\b", "cut it, or use 'look at'"),
    ("worth-noting", r"\bit(?:'|’)?s worth noting\b|\bit is worth noting\b", "filler, delete and state the point"),
    ("todays-world", r"\bin today(?:'|’)?s\s+(?:[\w-]+\s+)*world\b", "filler opener"),
    ("when-it-comes", r"\bwhen it comes to\b", "use 'for' or 'with'"),
    ("landscape", r"\bnavigat(?:e|es|ing)\s+the\s+(?:[\w-]+\s+)?landscape\b", "metaphor with no content"),
    ("testament", r"\ba testament to\b", "say what it shows"),
    ("crucial-role", r"\bplays? an?\s+(?:crucial|vital|pivotal|key|critical|significant)\s+role\b", "say what it does"),
    ("end-of-day", r"\bat the end of the day\b", "filler"),
    ("unlock", r"\bunlock(?:ing|s)?\s+(?:the\s+)?(?:full\s+)?potential\b", "marketing phrasing"),
    ("next-level", r"\bto the next level\b", "marketing phrasing"),
    ("dive-in", r"\b(?:let(?:'|’)?s\s+)?(?:dive|dives|diving)\s+(?:in|into|deep)\b|\bdeep dive\b", "filler opener"),
    ("seamless", r"\bseamless(?:ly)?\b", "say what does not break"),
    ("elevate", r"\belevat(?:e|es|ing)\s+your\b", "marketing phrasing"),
    ("game-changer", r"\bgame[-\s]chang(?:er|ers|ing)\b", "marketing phrasing"),
    ("realm", r"\bin the realm of\b", "use 'in'"),
    ("embark", r"\bembark(?:s|ing)?\s+on\b", "use 'start'"),
    ("tapestry", r"\btapestry\b", "metaphor with no content"),
    ("meticulous", r"\bmeticulous(?:ly)?\b", "cut it"),
    ("boasts", r"\bboasts?\b", "use 'has'"),
    ("paradigm", r"\bparadigm shift\b", "say what changed"),
    ("synergy", r"\bsynerg(?:y|ies|istic)\b", "cut it"),
    ("revolutionize", r"\brevolutioniz(?:e|es|ed|ing)\b", "marketing phrasing"),
    ("empower", r"\bempower(?:s|ed|ing)?\b", "say what it lets someone do"),
    ("holistic", r"\bholistic\b", "cut it"),
    ("harness", r"\bharness(?:es|ing)?\s+the\s+power\b", "marketing phrasing"),
    ("no-denying", r"\bthere(?:'|’)?s no denying\b", "filler"),
    ("underscores", r"\bunderscor(?:e|es|ing)\s+the\s+importance\b", "say why it matters"),
    ("cutting-edge", r"\bcutting[-\s]edge\b", "name the actual technique"),
    ("utilize", r"\butiliz(?:e|es|ed|ing|ation)\b", "use 'use'"),
    ("closer", r"^\s*(?:in conclusion|in summary|to summarize|to sum up)\b", "filler closer"),
    ("not-only", r"\bnot only\b.{0,80}?\bbut also\b", "padding, say the second half"),
    ("isnt-just", r"\b(?:is|are|isn(?:'|’)?t|aren(?:'|’)?t)\s+(?:just|merely|simply)\s+(?:[\w-]+\s+){0,3}[\w-]+[,;]\s*(?:it|they|this)\b", "inflated contrast, say the claim"),
    ("world-of", r"\bthe world of\b", "cut the wrapper"),
    ("ever-changing", r"\bever[-\s](?:changing|evolving|growing)\b", "filler modifier"),
    ("fast-paced", r"\bfast[-\s]paced\b", "filler modifier"),
    ("whether-youre", r"\bwhether you(?:'|’)?re\b", "audience-flattering filler"),
    ("say-goodbye", r"\bsay goodbye to\b", "marketing phrasing"),
    ("look-no-further", r"\blook no further\b", "marketing phrasing"),
]

TELLS_MEDIUM = [
    ("robust", r"\brobust(?:ness)?\b", "fine in stats or optimization, decoration elsewhere"),
    ("comprehensive", r"\bcomprehensive(?:ly)?\b", "usually decoration"),
    ("leverage", r"\bleverag(?:e|es|ed|ing)\b", "use 'use'"),
    ("streamline", r"\bstreamlin(?:e|es|ed|ing)\b", "say what got shorter"),
    ("crucial", r"\b(?:crucial|vital|essential|paramount)\b", "usually decoration"),
    ("powerful", r"\bpowerful\b", "say what it can do"),
    ("myriad", r"\bmyriad\b", "use 'many' or a number"),
    ("wide-range", r"\ba\s+(?:wide|broad|vast)\s+(?:range|variety|array)\s+of\b", "use a number"),
    ("wealth-of", r"\ba wealth of\b", "use a number"),
    ("sota", r"\bstate[-\s]of[-\s]the[-\s]art\b", "fine in related work, decoration elsewhere"),
    ("best-in-class", r"\bbest[-\s]in[-\s]class\b", "unfalsifiable"),
    ("in-order-to", r"\bin order to\b", "use 'to'"),
    ("connector", r"^\s*(?:furthermore|moreover|additionally)\b", "start on the claim"),
    ("aims-to", r"\baims? to\b", "say whether it does"),
    ("showcase", r"\bshowcas(?:e|es|ed|ing)\b", "use 'show'"),
    ("foster", r"\bfoster(?:s|ed|ing)?\b", "use a concrete verb"),
    ("bespoke", r"\bbespoke\b", "use 'custom'"),
    ("significantly", r"\bsignificantly\b", "give the number, or reserve for statistical significance"),
]

HEDGES = r"\b(?:might|may|could|perhaps|possibly|potentially|somewhat|arguably|seemingly|relatively|fairly|quite|rather|to some extent|in some cases)\b"

EM_DASH = "—"
EN_DASH = "–"

MAX_BULLET_WORDS = 40
MAX_BULLET_RUN = 8
MAX_SENTENCE_WORDS = 45


# --------------------------------------------------------------------------
# Masking
# --------------------------------------------------------------------------

def _blank(match: re.Match) -> str:
    """Replace a match with spaces so column numbers stay correct."""
    return " " * len(match.group(0))


_MASKS = [
    re.compile(r"`[^`]*`"),                 # inline code
    re.compile(r"\]\([^)]*\)"),             # markdown link targets
    re.compile(r"https?://\S+"),            # bare URLs
    re.compile(r"<!--.*?-->"),              # html comments
    re.compile(r"<[^>]+>"),                 # html tags, keeps the text between them
]


def mask(line: str) -> str:
    for pattern in _MASKS:
        line = pattern.sub(_blank, line)
    return line


def masked_lines(text: str) -> list[str]:
    """Return each line masked, with fenced code blocks and lint-off regions blanked."""
    out: list[str] = []
    in_fence = False
    linting = True
    for raw in text.splitlines():
        stripped = raw.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append("")
            continue
        low = raw.lower()
        if "prose-lint: off" in low:
            linting = False
            out.append("")
            continue
        if "prose-lint: on" in low:
            linting = True
            out.append("")
            continue
        out.append(mask(raw) if (linting and not in_fence) else "")
    return out


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

class Finding:
    __slots__ = ("path", "line", "col", "rule", "severity", "message")

    def __init__(self, path, line, col, rule, severity, message):
        self.path, self.line, self.col = path, line, col
        self.rule, self.severity, self.message = rule, severity, message

    def as_dict(self) -> dict:
        return {
            "path": self.path, "line": self.line, "col": self.col,
            "rule": self.rule, "severity": self.severity, "message": self.message,
        }

    def __str__(self) -> str:
        return f"{self.path}:{self.line}:{self.col} [{self.severity[0].upper()}:{self.rule}] {self.message}"


_COMPILED = (
    [(rid, "high", re.compile(pat, re.I), msg) for rid, pat, msg in TELLS_HIGH]
    + [(rid, "medium", re.compile(pat, re.I), msg) for rid, pat, msg in TELLS_MEDIUM]
)
_HEDGE_RE = re.compile(HEDGES, re.I)
_BULLET_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’-]*")


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def check_file(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = masked_lines(text)
    rel = _display_path(path)

    for i, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        # Em dashes and en dashes used as em dashes.
        for m in re.finditer(re.escape(EM_DASH), line):
            findings.append(Finding(rel, i, m.start() + 1, "em-dash", "high",
                                    "em dash, use a comma, colon, period, or parentheses"))
        for m in re.finditer(r"\s" + re.escape(EN_DASH) + r"\s|\s--\s", line):
            findings.append(Finding(rel, i, m.start() + 1, "em-dash-alt", "medium",
                                    "dash used as an em dash, rewrite the clause"))

        # Vocabulary tells.
        for rule_id, sev, pattern, msg in _COMPILED:
            for m in pattern.finditer(line):
                findings.append(Finding(rel, i, m.start() + 1, rule_id, sev,
                                        f"'{m.group(0).strip()}': {msg}"))

        # Sentence-level checks.
        for sentence in _SENTENCE_SPLIT.split(line):
            words = _WORD_RE.findall(sentence)
            if len(words) > MAX_SENTENCE_WORDS:
                findings.append(Finding(rel, i, 1, "long-sentence", "medium",
                                        f"{len(words)} words in one sentence, split it"))
            hedges = _HEDGE_RE.findall(sentence)
            if len(hedges) >= 2:
                joined = ", ".join(sorted({h.lower() for h in hedges}))
                findings.append(Finding(rel, i, 1, "hedge-stack", "medium",
                                        f"stacked hedges ({joined}), keep at most one"))

    findings.extend(_check_bullets(rel, lines))
    findings.sort(key=lambda f: (f.line, f.col, f.rule))
    return findings


def _check_bullets(rel: str, lines: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    run_start = None
    run_len = 0
    current = None  # (line_no, indent, [text parts])

    def flush_bullet():
        if current is None:
            return
        line_no, _, parts = current
        words = _WORD_RE.findall(" ".join(parts))
        if len(words) > MAX_BULLET_WORDS:
            findings.append(Finding(rel, line_no, 1, "bullet-bloat", "medium",
                                    f"{len(words)}-word bullet, write it as a paragraph"))

    def flush_run():
        if run_start is not None and run_len > MAX_BULLET_RUN:
            findings.append(Finding(rel, run_start, 1, "bullet-run", "medium",
                                    f"{run_len} consecutive bullets, use a table or sections"))

    for i, line in enumerate(lines, start=1):
        m = _BULLET_RE.match(line)
        if m:
            flush_bullet()
            current = (i, len(m.group(1)), [m.group(2)])
            if run_start is None:
                run_start, run_len = i, 1
            else:
                run_len += 1
            continue
        if not line.strip():
            flush_bullet()
            current = None
            flush_run()
            run_start, run_len = None, 0
            continue
        if current is not None and line.startswith(" "):
            current[2].append(line.strip())

    flush_bullet()
    flush_run()
    return findings


# --------------------------------------------------------------------------
# Fixing
# --------------------------------------------------------------------------

def fix_em_dashes(text: str) -> tuple[str, int]:
    """Rewrite only the unambiguous em dash forms. Everything else is left alone."""
    out_lines = []
    count = 0
    in_fence = False
    for raw in text.splitlines():
        stripped = raw.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out_lines.append(raw)
            continue
        if in_fence or EM_DASH not in raw:
            out_lines.append(raw)
            continue
        new = re.sub(r"\s*" + re.escape(EM_DASH) + r"\s*", ", ", raw)
        new = re.sub(r",\s*,", ",", new)
        new = re.sub(r"\s+,", ",", new)
        count += raw.count(EM_DASH)
        out_lines.append(new)
    trailing = "\n" if text.endswith("\n") else ""
    return "\n".join(out_lines) + trailing, count


# --------------------------------------------------------------------------
# File discovery
# --------------------------------------------------------------------------

def git_tracked_markdown(root: Path) -> list[Path]:
    """Tracked markdown plus untracked-but-not-ignored markdown.

    Untracked files are included deliberately: a file staged for its first
    commit is exactly the one most likely to need linting, and leaving it out
    lets new prose land unchecked.
    """
    names: list[str] = []
    for extra in ([], ["--others", "--exclude-standard"]):
        try:
            result = subprocess.run(
                ["git", "ls-files", *extra, "*.md", "*.markdown"],
                cwd=root, capture_output=True, text=True, check=True,
            )
            names.extend(p for p in result.stdout.splitlines() if p.strip())
        except (subprocess.CalledProcessError, FileNotFoundError):
            return walk_markdown(root)

    paths = [root / n for n in dict.fromkeys(names)]
    return paths if paths else walk_markdown(root)


def walk_markdown(root: Path) -> list[Path]:
    found = []
    for path in root.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        found.append(path)
    return sorted(found)


def resolve_targets(args_paths: list[str]) -> list[Path]:
    root = Path.cwd()
    if not args_paths:
        return git_tracked_markdown(root)
    targets: list[Path] = []
    for raw in args_paths:
        p = Path(raw)
        if p.is_dir():
            targets.extend(walk_markdown(p))
        elif p.is_file():
            targets.append(p)
        else:
            print(f"warning: no such path: {raw}", file=sys.stderr)
    return targets


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint prose for em dashes, AI tells, and bloat.")
    parser.add_argument("paths", nargs="*", help="files or directories, default is every tracked .md")
    parser.add_argument("--fail-on", choices=SEVERITIES, default="high",
                        help="minimum severity that makes this exit nonzero (default: high)")
    parser.add_argument("--min-severity", choices=SEVERITIES, default="medium",
                        help="minimum severity to report (default: medium)")
    parser.add_argument("--fix", action="store_true", help="rewrite unambiguous em dashes in place")
    parser.add_argument("--stats", action="store_true", help="print counts by rule instead of findings")
    parser.add_argument("--json", dest="as_json", action="store_true", help="emit JSON")
    parser.add_argument("--exclude", action="append", default=[], help="substring of paths to skip, repeatable")
    args = parser.parse_args(argv)

    targets = resolve_targets(args.paths)
    if args.exclude:
        targets = [t for t in targets if not any(x in t.as_posix() for x in args.exclude)]
    if not targets:
        print("no markdown files found", file=sys.stderr)
        return 0

    if args.fix:
        fixed_files = 0
        fixed_dashes = 0
        for path in targets:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            new_text, n = fix_em_dashes(text)
            if n:
                path.write_text(new_text, encoding="utf-8")
                fixed_files += 1
                fixed_dashes += n
        print(f"fixed {fixed_dashes} em dash(es) across {fixed_files} file(s); re-read those lines")

    findings: list[Finding] = []
    for path in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
            continue
        findings.extend(check_file(path, text))

    threshold = SEVERITIES.index(args.min_severity)
    findings = [f for f in findings if SEVERITIES.index(f.severity) >= threshold]

    if args.as_json:
        print(json.dumps([f.as_dict() for f in findings], indent=2))
    elif args.stats:
        counts: dict[tuple[str, str], int] = {}
        for f in findings:
            counts[(f.severity, f.rule)] = counts.get((f.severity, f.rule), 0) + 1
        for (sev, rule), n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"{n:4d}  {sev:6s}  {rule}")
        print(f"\n{len(findings)} finding(s) across {len(targets)} file(s)")
    else:
        for f in findings:
            print(f)
        if not findings:
            print(f"clean: {len(targets)} file(s)")

    fail_at = SEVERITIES.index(args.fail_on)
    failures = [f for f in findings if SEVERITIES.index(f.severity) >= fail_at]
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
