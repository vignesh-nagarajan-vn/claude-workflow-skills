#!/usr/bin/env python3
"""Cross-check every number in a paper or report against the run artifacts it
should have come from, and list the ones with no source.

Matching allows for rounding: a paper reporting 0.847 is traced to an artifact
value of 0.84723, because the paper's own precision sets the tolerance.

Stdlib only.

    python trace_claims.py paper/main.tex
    python trace_claims.py paper/main.tex --results results/07-12-2026
    python trace_claims.py report.md --include-integers
    python trace_claims.py paper/main.tex --json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

ARTIFACT_EXT = {".csv", ".tsv", ".json", ".md", ".txt", ".log", ".yml", ".yaml"}
RESULT_DIR_NAMES = ("results", "outputs", "output", "artifacts", "runs", "run")
MAX_BYTES = 20_000_000
MAX_PLACES = 8

NUMBER_RE = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*(\\?%)?")

# LaTeX commands whose numeric arguments are never claims.
NOISE_CMD_RE = re.compile(
    r"\\(?:cite[a-zA-Z]*|ref|eqref|pageref|autoref|label|ccsdesc|acmDOI|acmISBN|acmYear"
    r"|acmVolume|acmNumber|acmArticle|acmMonth|copyrightyear|setcopyright|bibliography"
    r"|includegraphics|vspace|hspace|setlength|hline|cline|arraystretch|columnwidth"
    r"|textwidth|linewidth|documentclass|usepackage|input|include|url|href|doi)"
    r"\s*(?:\[[^\]]*\])?\s*(?:\{[^{}]*\})?",
    re.I,
)
INLINE_VERBATIM_RE = re.compile(r"\\verb\|[^|]*\||\\texttt\{[^{}]*\}")
COMMENT_RE = re.compile(r"(?<!\\)%.*$")
MD_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _git(args: list[str]) -> str:
    try:
        r = subprocess.run(["git"] + args, capture_output=True, text=True, check=True)
        return r.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


# --------------------------------------------------------------------------
# Source side
# --------------------------------------------------------------------------

def strip_noise(line: str, is_tex: bool) -> str:
    if is_tex:
        line = COMMENT_RE.sub("", line)
        line = INLINE_VERBATIM_RE.sub(" ", line)
        line = NOISE_CMD_RE.sub(" ", line)
    return line


def decimal_places(token: str) -> int:
    """Precision a number is written at: 0.847 -> 3, 1.5e-3 -> 4, 12 -> 0."""
    try:
        return max(0, -Decimal(token).as_tuple().exponent)
    except (InvalidOperation, TypeError):
        return 0


def is_claim(text: str, is_percent: bool, min_decimals: int, include_integers: bool) -> bool:
    digits = text.lstrip("-").split("e")[0].split("E")[0].replace(".", "")
    if len(digits) > 8:
        return False                      # ACM concept ids, DOIs, hashes
    if is_percent:
        # 84.7% is the fraction 0.847, so a percent carries two more places of
        # precision than it shows.
        return decimal_places(text) + 2 >= min_decimals
    if "." in text:
        return decimal_places(text) >= min_decimals
    if not include_integers:
        return False
    value = abs(float(text))
    if 1900 <= value <= 2099:
        return False                      # citation and copyright years
    return value >= 1000


def extract_claims(path: Path, min_decimals: int, include_integers: bool) -> list[dict]:
    is_tex = path.suffix.lower() in {".tex", ".ltx"}
    claims: list[dict] = []
    in_fence = False

    for lineno, raw in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if not is_tex and MD_FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        line = strip_noise(raw, is_tex)
        for m in NUMBER_RE.finditer(line):
            token, pct = m.group(1), bool(m.group(2))
            if not is_claim(token, pct, min_decimals, include_integers):
                continue
            context = " ".join(raw.split())
            if len(context) > 74:
                start = max(0, m.start() - 30)
                context = "..." + context[start:start + 71].strip() + "..."
            claims.append({"value": token, "line": lineno, "percent": pct, "context": context})
    return claims


# --------------------------------------------------------------------------
# Artifact side
# --------------------------------------------------------------------------

def find_results_dir(root: Path, explicit: str | None) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.is_dir() else (root / explicit if (root / explicit).is_dir() else None)
    best = None
    for name in RESULT_DIR_NAMES:
        for candidate in sorted(root.rglob(name)):
            if not candidate.is_dir() or any(
                part in {".git", "node_modules", ".venv"} for part in candidate.parts
            ):
                continue
            if best is None or len(candidate.parts) < len(best.parts):
                best = candidate
    return best


def artifact_values(results: Path) -> tuple[dict[str, set[str]], dict[str, int], int]:
    """Index rounded string forms to the artifact files and distinct-value counts
    behind them.

    The count is what makes the result meaningful. A run directory holds tens of
    thousands of numbers, so at two decimal places something always rounds to any
    value you name. Knowing that 812 distinct values match is the difference
    between a trace and a coincidence.
    """
    seen: dict[float, set[str]] = {}
    files = 0

    for path in sorted(results.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in ARTIFACT_EXT:
            continue
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        files += 1

        raw_numbers: list[str] = []
        if path.suffix.lower() in {".csv", ".tsv"}:
            delim = "\t" if path.suffix.lower() == ".tsv" else ","
            try:
                for row in csv.reader(text.splitlines(), delimiter=delim):
                    raw_numbers.extend(cell.strip() for cell in row)
            except csv.Error:
                raw_numbers.extend(re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text))
        else:
            raw_numbers.extend(re.findall(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", text))

        rel = path.relative_to(results).as_posix()
        for token in raw_numbers:
            try:
                value = float(token)
            except (TypeError, ValueError):
                continue
            bucket = seen.setdefault(value, set())
            if len(bucket) < 6:
                bucket.add(rel)

    index: dict[str, set[str]] = {}
    counts: dict[str, int] = {}
    for value, owners in seen.items():
        for places in range(0, MAX_PLACES + 1):
            # A set, so a positive value is counted once, not once per spelling.
            for magnitude in {value, abs(value)}:
                form = f"{magnitude:.{places}f}"
                counts[form] = counts.get(form, 0) + 1
                slot = index.setdefault(form, set())
                if len(slot) < 6:
                    slot |= owners

    return index, counts, files


def normalize(token: str, percent: bool = False) -> list[str]:
    """Rounded forms an artifact value must match. A percent also matches its
    fraction, so 84.7% traces to 0.847 as well as to 84.7."""
    try:
        value = float(token)
    except ValueError:
        return []
    places = decimal_places(token)
    candidates = [(value, places)]
    if percent:
        candidates.append((value / 100, places + 2))
    forms = set()
    for number, digits in candidates:
        if digits > MAX_PLACES:
            continue
        forms.add(f"{number:.{digits}f}")
        forms.add(f"{abs(number):.{digits}f}")
    return sorted(forms)


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def render(source: Path, results: Path, files: int, claims: list[dict]) -> str:
    untraced = [c for c in claims if c["status"] == "untraced"]
    weak = [c for c in claims if c["status"] == "ambiguous"]
    traced = [c for c in claims if c["status"] == "traced"]

    out = [f"CLAIM TRACE  {source.as_posix()}",
           f"  artifacts: {results.as_posix()} ({files} file(s))",
           f"  traced {len(traced)}, ambiguous {len(weak)}, untraced {len(untraced)}"]

    if untraced:
        out.append("")
        out.append(f"untraced ({len(untraced)}), no artifact value rounds to this:")
        width = max(len(u["value"]) for u in untraced) + 2
        for u in untraced:
            out.append(f"  line {u['line']:>5}  {u['value']:<{width}} {u['context']}")

    if traced:
        out.append("")
        out.append(f"traced ({len(traced)}), few enough matches to be real provenance:")
        width = max(len(t["value"]) for t in traced) + 2
        for t in traced:
            where = ", ".join(sorted(t["files"])[:2])
            out.append(f"  line {t['line']:>5}  {t['value']:<{width}} {where}")

    if weak:
        out.append("")
        out.append(f"ambiguous ({len(weak)}), too many artifact values match to be evidence:")
        width = max(len(w["value"]) for w in weak) + 2
        shown = weak[:12]
        for w in shown:
            out.append(f"  line {w['line']:>5}  {w['value']:<{width}} {w['matches']} values match")
        if len(weak) > len(shown):
            out.append(f"  ... and {len(weak) - len(shown)} more")
        out.append("")
        out.append("  Ambiguous is not a failure. It means the number is reported at too few")
        out.append("  decimals to pin down against this many artifacts. Check those by hand,")
        out.append("  or re-run with --min-decimals 3 to look only at precise claims.")

    if not untraced and not weak:
        out.append("")
        out.append("every number traces to a specific artifact value")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Trace paper numbers to run artifacts.")
    parser.add_argument("source", help="the .tex or .md file whose numbers are claims")
    parser.add_argument("--results", help="artifact directory (auto-detected otherwise)")
    parser.add_argument("--min-decimals", type=int, default=2,
                        help="decimals required to count as a claim (default: 2)")
    parser.add_argument("--include-integers", action="store_true",
                        help="also check integers of 1000 or more")
    parser.add_argument("--max-matches", type=int, default=5,
                        help="distinct artifact values that may match before a number "
                             "counts as ambiguous rather than traced (default: 5)")
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(_git(["rev-parse", "--show-toplevel"]).strip() or Path.cwd())
    source = Path(args.source)
    if not source.is_file():
        source = root / args.source
    if not source.is_file():
        print(f"no such file: {args.source}", file=sys.stderr)
        return 2

    results = find_results_dir(root, args.results)
    if results is None:
        print("no results directory found, pass --results", file=sys.stderr)
        return 2

    claims = extract_claims(source, args.min_decimals, args.include_integers)
    if not claims:
        print("no claim-shaped numbers found; try --min-decimals 1 or --include-integers")
        return 0

    index, counts, files = artifact_values(results)

    for claim in claims:
        forms = normalize(claim["value"], claim["percent"])
        matches = max((counts.get(f, 0) for f in forms), default=0)
        owners: set[str] = set()
        for f in forms:
            owners |= index.get(f, set())
        claim["matches"] = matches
        claim["files"] = sorted(owners)
        if matches == 0:
            claim["status"] = "untraced"
        elif matches <= args.max_matches:
            claim["status"] = "traced"
        else:
            claim["status"] = "ambiguous"

    if args.as_json:
        print(json.dumps({
            "source": source.as_posix(), "results": results.as_posix(),
            "artifact_files": files, "claims": claims,
        }, indent=2))
    else:
        print(render(source, results, files, claims))

    return 1 if any(c["status"] == "untraced" for c in claims) else 0


if __name__ == "__main__":
    sys.exit(main())
