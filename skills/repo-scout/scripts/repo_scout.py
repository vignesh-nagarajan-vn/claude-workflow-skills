#!/usr/bin/env python3
"""Emit a compact map of a repo so a session can skip exploratory file reads.

Stdlib only.

    python repo_scout.py
    python repo_scout.py --dir packages/core
    python repo_scout.py --since "7 days ago" --budget 60
    python repo_scout.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

TEXT_EXT = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java", ".kt",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".scala", ".sh", ".ps1",
    ".sql", ".css", ".scss", ".html", ".vue", ".svelte", ".lua", ".r", ".jl", ".tex",
    ".md", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".xml",
}
CODE_EXT = TEXT_EXT - {".md", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".xml"}
MAX_BYTES = 2_000_000
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
             ".next", ".turbo", "target", "vendor", "site-packages"}

FRAMEWORKS = {
    "next": "Next.js", "react": "React", "vue": "Vue", "svelte": "Svelte",
    "@sveltejs/kit": "SvelteKit", "express": "Express", "fastify": "Fastify",
    "vite": "Vite", "astro": "Astro", "@nestjs/core": "NestJS",
    "@anthropic-ai/sdk": "Anthropic SDK", "openai": "OpenAI SDK",
    "tailwindcss": "Tailwind", "zod": "Zod", "vitest": "Vitest", "jest": "Jest",
}
PY_LIBS = {
    "torch": "PyTorch", "tensorflow": "TensorFlow", "numpy": "NumPy", "pandas": "pandas",
    "scipy": "SciPy", "sklearn": "scikit-learn", "scikit-learn": "scikit-learn",
    "fastapi": "FastAPI", "django": "Django", "flask": "Flask", "streamlit": "Streamlit",
    "anthropic": "Anthropic SDK", "openai": "OpenAI SDK", "pytest": "pytest",
    "matplotlib": "matplotlib", "transformers": "transformers",
}
ENTRY_CANDIDATES = [
    "main.py", "__main__.py", "app.py", "manage.py", "cli.py", "run.py",
    "index.ts", "index.js", "main.ts", "main.go", "main.rs", "src/index.ts",
    "src/main.ts", "src/main.py", "app/page.tsx", "app/layout.tsx", "pages/index.tsx",
]


# --------------------------------------------------------------------------
# Collection
# --------------------------------------------------------------------------

def _git(args: list[str]) -> str:
    try:
        r = subprocess.run(["git"] + args, capture_output=True, text=True, check=True)
        return r.stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def list_files(root: Path, scope: str | None) -> list[Path]:
    out = _git(["ls-files"])
    if out:
        paths = [root / p.strip() for p in out.splitlines() if p.strip()]
    else:
        paths = [p for p in root.rglob("*")
                 if p.is_file() and not any(d in p.parts for d in SKIP_DIRS)]
    if scope:
        prefix = (root / scope).resolve()
        paths = [p for p in paths if str(p.resolve()).startswith(str(prefix))]
    return [p for p in paths if p.is_file()]


def count_lines(path: Path) -> int:
    try:
        if path.stat().st_size > MAX_BYTES:
            return 0
        with path.open("rb") as fh:
            return fh.read().count(b"\n") + 1
    except OSError:
        return 0


EXT_LANG = {
    ".py": "python", ".ts": "typescript", ".tsx": "typescript", ".js": "javascript",
    ".jsx": "javascript", ".mjs": "javascript", ".go": "go", ".rs": "rust",
    ".java": "java", ".kt": "kotlin", ".c": "c", ".h": "c", ".cpp": "c++",
    ".hpp": "c++", ".cs": "c#", ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".scala": "scala", ".sh": "shell", ".ps1": "powershell", ".sql": "sql",
    ".css": "css", ".scss": "css", ".html": "html", ".vue": "vue",
    ".svelte": "svelte", ".lua": "lua", ".r": "r", ".jl": "julia", ".tex": "latex",
}
RUNNER_RE = re.compile(
    r"(^|/)(main|__main__|cli|app|run|run_all|train|serve|server|manage|index)\.(py|ts|js|go|rs)$"
)


def detect_languages(names: list[str]) -> str:
    counts: Counter = Counter()
    for name in names:
        lang = EXT_LANG.get(Path(name).suffix.lower())
        if lang:
            counts[lang] += 1
    top = counts.most_common(4)
    return ", ".join(f"{lang} {n}" for lang, n in top)


def _nearest(names: list[str], filename: str, limit: int = 3) -> list[str]:
    """Manifests at any depth, shallowest first, so nested projects are found."""
    hits = [n for n in names if n == filename or n.endswith("/" + filename)]
    hits.sort(key=lambda n: (n.count("/"), n))
    return hits[:limit]


def detect_stack(root: Path, names: list[str]) -> list[str]:
    found: list[str] = []

    # Merge deps across the shallowest few package.json files so a monorepo root,
    # which usually declares almost nothing, still reports its real stack.
    pkg_hits = _nearest(names, "package.json", limit=6)
    deps: dict[str, str] = {}
    for hit in pkg_hits:
        pkg = root / hit
        if not pkg.is_file():
            continue
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        deps.update(data.get("dependencies", {}) or {})
        deps.update(data.get("devDependencies", {}) or {})

    if pkg_hits:
        labels = [FRAMEWORKS[d] for d in deps if d in FRAMEWORKS]
        if "next" in deps:
            major = re.sub(r"[^\d.]", "", deps["next"]).split(".")[0]
            labels = [f"Next.js {major}" if lab == "Next.js" else lab for lab in labels]
        if _nearest(names, "tsconfig.json"):
            labels.append("TypeScript")
        found.append("node: " + ", ".join(dict.fromkeys(labels)) if labels else "node")

    py_text = ""
    for base in ("pyproject.toml", "requirements.txt", "setup.py", "environment.yml"):
        for hit in _nearest(names, base):
            f = root / hit
            if f.is_file():
                try:
                    py_text += f.read_text(encoding="utf-8", errors="ignore").lower()
                except OSError:
                    pass
    if py_text:
        libs = sorted({label for key, label in PY_LIBS.items()
                       if re.search(rf"\b{re.escape(key)}\b", py_text)})
        found.append("python: " + ", ".join(libs) if libs else "python")

    for name, label in (("go.mod", "go"), ("Cargo.toml", "rust"),
                        ("pom.xml", "java/maven"), ("Gemfile", "ruby"),
                        ("Dockerfile", "docker"), ("docker-compose.yml", "docker-compose")):
        if (root / name).is_file():
            found.append(label)

    return found


def detect_entries(root: Path, files: set[str]) -> list[str]:
    entries = [c for c in ENTRY_CANDIDATES if c in files]

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            for key in ("main", "module", "bin"):
                val = data.get(key)
                if isinstance(val, str) and val.lstrip("./") in files:
                    entries.append(val.lstrip("./"))
                elif isinstance(val, dict):
                    entries.extend(v.lstrip("./") for v in val.values() if v.lstrip("./") in files)
        except (OSError, ValueError):
            pass

    api = sorted(f for f in files if re.search(r"(^|/)(route|handler)\.(ts|js|py)$", f))
    entries.extend(api[:5])

    if len(entries) < 6:
        runners = [f for f in files
                   if RUNNER_RE.search(f) and not any(d in f.split("/") for d in SKIP_DIRS)]
        runners.sort(key=lambda f: (f.count("/"), f))
        entries.extend(runners[:8])

    return list(dict.fromkeys(entries))[:10]


def hot_files(since: str, tracked: set[str]) -> list[tuple[str, int]]:
    out = _git(["log", f"--since={since}", "--name-only", "--pretty=format:"])
    if not out:
        return []
    counts = Counter(ln.strip() for ln in out.splitlines()
                     if ln.strip() and ln.strip() in tracked)
    return counts.most_common(8)


def build(root: Path, scope: str | None, since: str) -> dict:
    paths = list_files(root, scope)
    rel = {}
    for p in paths:
        try:
            rel[p.relative_to(root).as_posix()] = p
        except ValueError:
            continue

    code_lines: dict[str, int] = {}
    dir_files: Counter = Counter()
    dir_lines: Counter = Counter()
    total_lines = 0

    for name, path in rel.items():
        ext = path.suffix.lower()
        if ext not in TEXT_EXT:
            continue
        n = count_lines(path)
        total_lines += n
        top = name.split("/")[0] if "/" in name else "(root)"
        dir_files[top] += 1
        dir_lines[top] += n
        if ext in CODE_EXT:
            code_lines[name] = n

    docs = sorted(n for n in rel
                  if n.lower().endswith((".md", ".rst"))
                  and (n.count("/") == 0 or n.startswith("docs/")))

    names = list(rel)
    return {
        "root": root.name,
        "file_count": len(rel),
        "total_lines": total_lines,
        "languages": detect_languages(names),
        "stack": detect_stack(root, names),
        "entries": detect_entries(root, set(rel)),
        "dirs": [(d, dir_files[d], dir_lines[d])
                 for d, _ in dir_lines.most_common(10)],
        "largest": sorted(code_lines.items(), key=lambda kv: -kv[1])[:8],
        "hot": hot_files(since, set(rel)),
        "docs": docs[:12],
        "since": since,
    }


# --------------------------------------------------------------------------
# Render
# --------------------------------------------------------------------------

def _k(n: int) -> str:
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)


def render(info: dict, budget: int) -> str:
    out: list[str] = []
    out.append(f"REPO MAP  {info['root']}  ({info['file_count']} files, "
               f"{_k(info['total_lines'])} lines)")

    if info.get("languages"):
        out.append("")
        out.append("languages: " + info["languages"])
    if info["stack"]:
        out.append("stack: " + " | ".join(info["stack"]))

    if info["entries"]:
        out.append("")
        out.append("entry points:")
        out.extend(f"  {e}" for e in info["entries"])

    if info["dirs"]:
        out.append("")
        out.append("directories (by lines):")
        width = max(len(d) for d, _, _ in info["dirs"]) + 2
        for name, files, lines in info["dirs"]:
            out.append(f"  {name:<{width}} {files:>4} files  {_k(lines):>7}")

    if info["largest"]:
        out.append("")
        out.append("largest files:")
        width = max(len(p) for p, _ in info["largest"]) + 2
        for path, lines in info["largest"]:
            out.append(f"  {path:<{width}} {lines:>5}")

    if info["hot"]:
        out.append("")
        out.append(f"recently changed (since {info['since']}, by commits):")
        width = max(len(p) for p, _ in info["hot"]) + 2
        for path, n in info["hot"]:
            out.append(f"  {path:<{width}} {n:>3}")

    if info["docs"]:
        out.append("")
        out.append("docs: " + "  ".join(info["docs"]))

    if len(out) > budget:
        out = out[:budget] + [f"  ... trimmed to --budget {budget} lines"]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compact repo map for cheap orientation.")
    parser.add_argument("--dir", dest="scope", help="scope to a subdirectory")
    parser.add_argument("--since", default="30 days ago", help="window for recently changed")
    parser.add_argument("--budget", type=int, default=80, help="max output lines (default: 80)")
    parser.add_argument("--json", dest="as_json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    root = Path.cwd()
    top = _git(["rev-parse", "--show-toplevel"]).strip()
    if top:
        root = Path(top)

    info = build(root, args.scope, args.since)
    if info["file_count"] == 0:
        print("no files found; is this the right directory?", file=sys.stderr)
        return 1

    print(json.dumps(info, indent=2) if args.as_json else render(info, args.budget))
    return 0


if __name__ == "__main__":
    sys.exit(main())
