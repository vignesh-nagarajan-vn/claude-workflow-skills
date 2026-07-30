#!/usr/bin/env python3
"""Gate an eval run against declared thresholds, and against a baseline run.

A metric with a threshold that is missing from the results counts as a failure.
Silently dropping a metric is the most common way an eval suite stops testing
what it claims to test.

Stdlib only.

    python check_thresholds.py results.json --thresholds evals/thresholds.json
    python check_thresholds.py results.json --baseline evals/baseline.json
    python check_thresholds.py results.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_THRESHOLDS = "evals/thresholds.json"


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    except ValueError as exc:
        print(f"error: {path} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(2)


def dig(data: dict, dotted: str):
    """Look up 'quality.accuracy' in nested results."""
    node = data
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node if isinstance(node, (int, float)) and not isinstance(node, bool) else None


def evaluate(results: dict, thresholds: dict, baseline: dict | None) -> list[dict]:
    rows: list[dict] = []

    for metric, rule in thresholds.items():
        if not isinstance(rule, dict):
            rule = {"min": rule}
        value = dig(results, metric)
        warn_only = bool(rule.get("warn_only"))

        if value is None:
            rows.append({"metric": metric, "status": "missing", "value": None,
                         "detail": "declared in thresholds, absent from results",
                         "warn_only": warn_only})
            continue

        failures: list[str] = []
        if "min" in rule and value < rule["min"]:
            failures.append(f"{value:g} < min {rule['min']:g}")
        if "max" in rule and value > rule["max"]:
            failures.append(f"{value:g} > max {rule['max']:g}")

        if baseline is not None:
            prior = dig(baseline, metric)
            if prior is not None:
                delta = value - prior
                if "max_drop" in rule and -delta > rule["max_drop"]:
                    failures.append(f"dropped {abs(delta):g} from {prior:g}, "
                                    f"limit {rule['max_drop']:g}")
                if "max_rise" in rule and delta > rule["max_rise"]:
                    failures.append(f"rose {delta:g} from {prior:g}, "
                                    f"limit {rule['max_rise']:g}")

        bounds = []
        if "min" in rule:
            bounds.append(f">= {rule['min']:g}")
        if "max" in rule:
            bounds.append(f"<= {rule['max']:g}")

        rows.append({
            "metric": metric,
            "value": value,
            "status": ("pass" if not failures else ("warn" if warn_only else "fail")),
            "detail": "; ".join(failures) if failures else " and ".join(bounds) or "no bounds",
            "warn_only": warn_only,
        })

    extra = [k for k in results if k not in thresholds and dig(results, k) is not None]
    for metric in sorted(extra):
        rows.append({"metric": metric, "value": dig(results, metric), "status": "ungated",
                     "detail": "reported but no threshold declared", "warn_only": False})
    return rows


def render(rows: list[dict], results_path: Path, thresholds_path: Path) -> str:
    label = {"pass": "PASS", "fail": "FAIL", "warn": "WARN",
             "missing": "MISS", "ungated": "  . "}
    order = {"fail": 0, "missing": 1, "warn": 2, "pass": 3, "ungated": 4}

    out = [f"EVAL THRESHOLDS  {results_path.as_posix()} vs {thresholds_path.as_posix()}", ""]
    width = max((len(r["metric"]) for r in rows), default=10) + 2

    for row in sorted(rows, key=lambda r: (order[r["status"]], r["metric"])):
        value = "n/a" if row["value"] is None else f"{row['value']:g}"
        out.append(f"  {label[row['status']]}  {row['metric']:<{width}} {value:>10}   {row['detail']}")

    counts = {k: sum(1 for r in rows if r["status"] == k) for k in order}
    out.append("")
    out.append(f"{counts['pass']} pass, {counts['fail']} fail, {counts['warn']} warn, "
               f"{counts['missing']} missing, {counts['ungated']} ungated")
    if counts["ungated"]:
        out.append("Ungated metrics are reported but nothing enforces them. "
                   "Add a threshold or stop reporting them.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate an eval run against thresholds.")
    parser.add_argument("results", help="results JSON from the eval run")
    parser.add_argument("--thresholds", default=DEFAULT_THRESHOLDS)
    parser.add_argument("--baseline", help="previous results JSON for regression checks")
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)

    results_path = Path(args.results)
    thresholds_path = Path(args.thresholds)
    if not results_path.is_file():
        print(f"no such file: {args.results}", file=sys.stderr)
        return 2
    if not thresholds_path.is_file():
        print(f"no thresholds at {args.thresholds}; declare them before gating",
              file=sys.stderr)
        return 2

    baseline = load(Path(args.baseline)) if args.baseline else None
    rows = evaluate(load(results_path), load(thresholds_path), baseline)

    if args.as_json:
        print(json.dumps(rows, indent=2))
    else:
        print(render(rows, results_path, thresholds_path))

    bad = [r for r in rows if r["status"] in ("fail", "missing")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
