#!/usr/bin/env python3
"""Copy the skills in this repo into ~/.claude/skills/.

Copies rather than symlinks, because Windows symlinks need Developer Mode or admin.

    python install.py               # install everything
    python install.py --dry-run     # show what would happen
    python install.py --force       # overwrite skills already installed
    python install.py --list        # list what is in this repo and what is installed
    python install.py prose-guard   # install one skill
    python install.py --uninstall prose-guard
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO_SKILLS = Path(__file__).resolve().parent / "skills"
DEST = Path.home() / ".claude" / "skills"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def available() -> list[Path]:
    if not REPO_SKILLS.is_dir():
        print(f"error: no skills directory at {REPO_SKILLS}", file=sys.stderr)
        sys.exit(2)
    return sorted(p for p in REPO_SKILLS.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())


def cmd_list() -> int:
    skills = available()
    print(f"repo:      {REPO_SKILLS}")
    print(f"installed: {DEST}\n")
    for path in skills:
        target = DEST / path.name
        if not target.exists():
            state = "not installed"
        elif _same(path, target):
            state = "up to date"
        else:
            state = "differs"
        print(f"  {path.name:<20} {state}")

    extra = []
    if DEST.is_dir():
        names = {p.name for p in skills}
        extra = sorted(p.name for p in DEST.iterdir() if p.is_dir() and p.name not in names)
    if extra:
        print("\n  installed from elsewhere: " + ", ".join(extra))
    return 0


def _same(src: Path, dst: Path) -> bool:
    src_files = {p.relative_to(src) for p in src.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    dst_files = {p.relative_to(dst) for p in dst.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    if src_files != dst_files:
        return False
    for rel in src_files:
        try:
            if (src / rel).read_bytes() != (dst / rel).read_bytes():
                return False
        except OSError:
            return False
    return True


def install(skills: list[Path], force: bool, dry_run: bool) -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    added = updated = skipped = 0

    for path in skills:
        target = DEST / path.name
        if target.exists():
            if _same(path, target):
                print(f"  = {path.name} (already up to date)")
                skipped += 1
                continue
            if not force:
                print(f"  ! {path.name} exists and differs, use --force to overwrite")
                skipped += 1
                continue
            if not dry_run:
                shutil.rmtree(target)
                shutil.copytree(path, target, ignore=IGNORE)
            print(f"  ~ {path.name} (overwritten)")
            updated += 1
        else:
            if not dry_run:
                shutil.copytree(path, target, ignore=IGNORE)
            print(f"  + {path.name}")
            added += 1

    verb = "would install" if dry_run else "installed"
    print(f"\n{verb}: {added} new, {updated} updated, {skipped} skipped -> {DEST}")
    if not dry_run and (added or updated):
        print("Restart or start a new Claude Code session to pick them up.")
    return 0


def uninstall(names: list[str], dry_run: bool) -> int:
    if not names:
        print("error: name at least one skill to uninstall", file=sys.stderr)
        return 2
    for name in names:
        target = DEST / name
        if not target.is_dir():
            print(f"  ? {name} is not installed")
            continue
        if not dry_run:
            shutil.rmtree(target)
        print(f"  - {name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install this repo's skills into ~/.claude/skills.")
    parser.add_argument("names", nargs="*", help="skill names, default is all of them")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen")
    parser.add_argument("--force", action="store_true", help="overwrite skills that already exist")
    parser.add_argument("--list", action="store_true", help="list repo and installed skills")
    parser.add_argument("--uninstall", action="store_true", help="remove the named skills")
    parser.add_argument("--dest", help="install somewhere other than ~/.claude/skills")
    args = parser.parse_args(argv)

    global DEST
    if args.dest:
        DEST = Path(args.dest).expanduser().resolve()

    if args.list:
        return cmd_list()
    if args.uninstall:
        return uninstall(args.names, args.dry_run)

    skills = available()
    if args.names:
        by_name = {p.name: p for p in skills}
        unknown = [n for n in args.names if n not in by_name]
        if unknown:
            print(f"error: unknown skill(s): {', '.join(unknown)}", file=sys.stderr)
            print(f"available: {', '.join(sorted(by_name))}", file=sys.stderr)
            return 2
        skills = [by_name[n] for n in args.names]

    if not skills:
        print("no skills found", file=sys.stderr)
        return 2

    return install(skills, args.force, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
