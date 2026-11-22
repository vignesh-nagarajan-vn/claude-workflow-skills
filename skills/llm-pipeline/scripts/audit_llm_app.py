#!/usr/bin/env python3
"""Audit an app that calls an LLM for key leakage, unvalidated model output, and
missing timeouts, and inventory which models it uses.

Deep checks run only on files that actually touch an LLM SDK, which keeps the
false-positive rate low.

Stdlib only.

    python audit_llm_app.py
    python audit_llm_app.py --dir apps/server
    python audit_llm_app.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py"}
WEB_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}
MAX_BYTES = 1_000_000

# An actual import, not just the package name, which also appears in dependency
# tables and docs.
SDK_RE = re.compile(
    r"(?:\bfrom|\brequire\(|\bimport)\s*['\"](?:@anthropic-ai/sdk|openai)['\"/]"
    r"|\bimport\s+anthropic\b|\bimport\s+openai\b|\bfrom\s+anthropic\b|\bfrom\s+openai\b"
)
# A bare messages.create also matches Twilio and Slack clients, so a call only
# counts when the same file also passes a model or a token cap.
CALL_RE = re.compile(r"messages\.(?:create|stream|parse)\s*\(|chat\.completions\.create\s*\(")
LLM_ARG_RE = re.compile(r"\bmax_(?:completion_)?tokens\b|\bmaxTokens\b|\bmodel\s*[=:]")
SCHEMA_RE = re.compile(r"\bfrom\s+['\"]zod['\"]|\brequire\(['\"]zod['\"]\)|\bz\.object\("
                       r"|\bpydantic\b|\bBaseModel\b|\bajv\b|\bvalibot\b|instructor")
MODEL_RE = re.compile(r"['\"](claude-[a-z0-9.\-]+|gpt-[a-z0-9.\-]+|o[134](?:-[a-z0-9]+)?)['\"]")

USE_CLIENT_RE = re.compile(r"^\s*['\"]use client['\"]")

# Only a real environment read counts. Naming the variable in docs copy or an
# error message is harmless, and matching the bare name flags all of that.
ENV_ACCESS = r"(?:process\.env|import\.meta\.env|os\.environ|os\.getenv)\s*[.\[(]\s*['\"]?"
API_KEY_RE = re.compile(ENV_ACCESS + r"[A-Z0-9_]*(?:ANTHROPIC|OPENAI|GEMINI|GROQ|MISTRAL)[A-Z0-9_]*KEY")
PUBLIC_SECRET_RE = re.compile(
    ENV_ACCESS + r"(?:NEXT_PUBLIC|VITE|REACT_APP)_[A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD)")
BROWSER_SDK_RE = re.compile(r"dangerouslyAllowBrowser\s*:\s*true")
PARSE_RE = re.compile(r"JSON\.parse\s*\(\s*([A-Za-z_$][\w$.]*)|json\.loads\s*\(\s*([A-Za-z_][\w.]*)")
MODEL_VAR_RE = re.compile(r"(completion|response|message|content|text|output|result|raw|reply|body)",
                          re.I)
MAX_DURATION_RE = re.compile(r"\bmaxDuration\b")
# maxDuration is a Next.js on Vercel setting, so only Next route conventions are
# checked: app router route files and pages/api handlers.
NEXT_ROUTE_RE = re.compile(r"(^|/)app/(.+/)?route\.(ts|js|mjs)$|(^|/)pages/api/.+\.(ts|js|mjs)$")


def _git(args: list[str], cwd: Path | None = None) -> str:
    try:
        r = subprocess.run(["git"] + args, capture_output=True, text=True, check=True, cwd=cwd)
        return r.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder)
        return True
    except ValueError:
        return False


def list_files(root: Path, scope: str | None) -> list[Path]:
    # From the root, so ls-files output joins onto root from any subdirectory.
    out = _git(["ls-files"], cwd=root)
    if out:
        paths = [root / p.strip() for p in out.splitlines() if p.strip()]
    else:
        paths = [p for p in root.rglob("*")
                 if p.is_file() and not any(d in p.parts for d in SKIP_DIRS)]
    paths = [p for p in paths if p.suffix.lower() in CODE_EXT and p.is_file()]
    if scope:
        folder = (root / scope).resolve()
        paths = [p for p in paths if _inside(p, folder)]
    return paths


def vercel_sets_duration(root: Path) -> bool:
    config = root / "vercel.json"
    try:
        return config.is_file() and "maxDuration" in config.read_text(encoding="utf-8")
    except OSError:
        return False


class Finding:
    def __init__(self, severity, rule, path, line, message):
        self.severity, self.rule = severity, rule
        self.path, self.line, self.message = path, line, message

    def as_dict(self):
        return {"severity": self.severity, "rule": self.rule, "path": self.path,
                "line": self.line, "message": self.message}

    def __str__(self):
        return f"{self.path}:{self.line} [{self.severity[0].upper()}:{self.rule}] {self.message}"


def audit(root: Path, scope: str | None) -> dict:
    findings: list[Finding] = []
    models: dict[str, set] = defaultdict(set)
    llm_files: list[str] = []
    duration_in_config = vercel_sets_duration(root)

    for path in list_files(root, scope):
        try:
            if path.stat().st_size > MAX_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        rel = path.relative_to(root).as_posix()
        lines = text.splitlines()
        head = "\n".join(lines[:20])
        is_web = path.suffix.lower() in WEB_EXT
        is_client = any(USE_CLIENT_RE.match(ln) for ln in lines[:10])
        touches_llm = bool(SDK_RE.search(text)) or bool(
            CALL_RE.search(text) and LLM_ARG_RE.search(text))
        if touches_llm:
            llm_files.append(rel)

        for i, line in enumerate(lines, start=1):
            for m in MODEL_RE.finditer(line):
                models[m.group(1)].add(rel)

            # Always-on leak checks: unambiguous regardless of the file's role.
            if PUBLIC_SECRET_RE.search(line):
                findings.append(Finding("high", "public-secret", rel, i,
                                        "secret in a client-exposed env var, it ships to the browser"))
            if BROWSER_SDK_RE.search(line):
                findings.append(Finding("high", "browser-sdk", rel, i,
                                        "dangerouslyAllowBrowser puts the key in the client bundle"))
            if is_web and is_client and API_KEY_RE.search(line):
                findings.append(Finding("high", "client-key", rel, i,
                                        "API key referenced in a 'use client' file"))

        if not touches_llm:
            continue

        # Deep checks, only where an SDK is actually in play.
        has_schema = bool(SCHEMA_RE.search(text))
        for i, line in enumerate(lines, start=1):
            m = PARSE_RE.search(line)
            if m and not has_schema:
                var = m.group(1) or m.group(2) or ""
                if MODEL_VAR_RE.search(var):
                    findings.append(Finding("medium", "unvalidated-output", rel, i,
                                            f"parsing '{var}' with no schema in this file, "
                                            "validate and repair instead"))

        if (NEXT_ROUTE_RE.search(rel) and not duration_in_config
                and not MAX_DURATION_RE.search(text)):
            findings.append(Finding("medium", "no-timeout", rel, 1,
                                    "Next.js route calls an LLM with no maxDuration, "
                                    "the platform default can cut long calls off"))

    return {
        "llm_files": sorted(llm_files),
        "findings": findings,
        "models": {k: sorted(v) for k, v in sorted(models.items())},
    }


def render(result: dict) -> str:
    out: list[str] = []
    findings = result["findings"]
    out.append(f"LLM AUDIT  ({len(result['llm_files'])} file(s) touch an SDK)")

    if findings:
        out.append("")
        order = {"high": 0, "medium": 1, "low": 2}
        for f in sorted(findings, key=lambda f: (order[f.severity], f.path, f.line)):
            out.append(f"  {f}")
    else:
        out.append("")
        out.append("  no leaks, unvalidated parses, or missing timeouts found")

    if result["models"]:
        out.append("")
        out.append("models in use:")
        width = max(len(m) for m in result["models"]) + 2
        for model, files in result["models"].items():
            shown = ", ".join(files[:3])
            more = f" (+{len(files) - 3})" if len(files) > 3 else ""
            out.append(f"  {model:<{width}} {shown}{more}")
        out.append("")
        out.append("  Check the tiering: retrieval, extraction, and classification belong on")
        out.append("  the cheap model. Reserve the expensive one for adjudication.")

    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit an LLM app for leaks and loose output handling.")
    parser.add_argument("--dir", dest="scope", help="scope to a subdirectory")
    parser.add_argument("--fail-on", choices=("high", "medium"), default="high")
    parser.add_argument("--json", dest="as_json", action="store_true")
    args = parser.parse_args(argv)

    root = Path(_git(["rev-parse", "--show-toplevel"]).strip() or Path.cwd())
    result = audit(root, args.scope)

    if args.as_json:
        print(json.dumps({
            "llm_files": result["llm_files"],
            "findings": [f.as_dict() for f in result["findings"]],
            "models": result["models"],
        }, indent=2))
    else:
        print(render(result))

    rank = {"high": 0, "medium": 1, "low": 2}
    threshold = rank[args.fail_on]
    fails = [f for f in result["findings"] if rank.get(f.severity, 2) <= threshold]
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
