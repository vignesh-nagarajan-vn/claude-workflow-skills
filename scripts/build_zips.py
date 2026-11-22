#!/usr/bin/env python3
"""Build one zip per skill for upload in the Claude app.

The app (Settings > Capabilities > Skills) takes one zip per skill, with the
skill folder as the archive root: repo-scout.zip unpacks to
repo-scout/SKILL.md, not skills/repo-scout/SKILL.md and not a bare SKILL.md.
Output is deterministic, so rebuilding an unchanged skill produces a
byte-identical file and zips/ stays quiet in diffs.

    python scripts/build_zips.py                 # build every skill into zips/
    python scripts/build_zips.py --skill repo-scout
    python scripts/build_zips.py --out somewhere/else
    python scripts/build_zips.py --check         # verify archives are current, write nothing
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"
DEFAULT_OUT = REPO / "zips"

# Pinned timestamp (zip cannot store dates before 1980), pinned entry order,
# and pinned compression are what make rebuilds byte-identical.
DATE_TIME = (2020, 1, 1, 0, 0, 0)
EXCLUDED_DIRS = {"__pycache__"}
EXCLUDED_NAMES = {".DS_Store", "Thumbs.db"}
EXCLUDED_SUFFIXES = {".pyc"}
# Text is archived with LF endings whatever the checkout uses, so a Windows
# clone with core.autocrlf builds the same bytes as everyone else.
TEXT_SUFFIXES = {".md", ".py", ".yml", ".yaml", ".json", ".txt", ".toml", ".cfg"}


def archived_bytes(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n")
    return data


def frontmatter_name(skill_md: Path) -> str | None:
    lines = skill_md.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return None


def validate(skill_dir: Path) -> list[str]:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_dir.name}: no SKILL.md at the skill root"]
    name = frontmatter_name(skill_md)
    if name is None:
        return [f"{skill_dir.name}: SKILL.md frontmatter has no name"]
    if name != skill_dir.name:
        return [f"{skill_dir.name}: frontmatter name '{name}' does not match the directory"]
    return []


def build_bytes(skill_dir: Path) -> bytes:
    entries = []
    for path in skill_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(skill_dir)
        if EXCLUDED_DIRS.intersection(rel.parts[:-1]):
            continue
        if path.name in EXCLUDED_NAMES or path.suffix in EXCLUDED_SUFFIXES:
            continue
        entries.append((f"{skill_dir.name}/{rel.as_posix()}", path))
    entries.sort()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for arcname, path in entries:
            info = zipfile.ZipInfo(arcname, date_time=DATE_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3  # ZipInfo's default differs by platform
            info.external_attr = 0o644 << 16
            archive.writestr(info, archived_bytes(path))
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build one deterministic zip per skill for the Claude app.")
    parser.add_argument("--skill", help="build only this skill")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory, default zips/")
    parser.add_argument("--check", action="store_true", help="verify existing archives are current, write nothing")
    args = parser.parse_args(argv)

    if args.skill:
        skill_dirs = [SKILLS / args.skill]
        if not skill_dirs[0].is_dir():
            print(f"error: no skill named {args.skill} under skills/", file=sys.stderr)
            return 2
    else:
        skill_dirs = sorted(p for p in SKILLS.iterdir() if p.is_dir())
        if not skill_dirs:
            print(f"error: no skills under {SKILLS}", file=sys.stderr)
            return 2

    problems = []
    for skill_dir in skill_dirs:
        problems += validate(skill_dir)
    if problems:
        for line in problems:
            print(f"error: {line}", file=sys.stderr)
        return 1

    stale = []
    for skill_dir in skill_dirs:
        data = build_bytes(skill_dir)
        target = args.out / f"{skill_dir.name}.zip"
        existed = target.is_file()
        current = existed and target.read_bytes() == data
        if args.check:
            if not current:
                stale.append(target)
                print(f"  ! {target.name} {'stale' if existed else 'missing'}")
        elif current:
            print(f"  = {target.name} (unchanged)")
        else:
            args.out.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            print(f"  {'~' if existed else '+'} {target.name}")

    # A full run also owns the rest of the output directory, so a renamed or
    # deleted skill does not leave its old archive behind.
    orphans = []
    if not args.skill and args.out.is_dir():
        expected = {f"{d.name}.zip" for d in skill_dirs}
        orphans = sorted(p for p in args.out.glob("*.zip") if p.name not in expected)
    for orphan in orphans:
        if args.check:
            print(f"  ! {orphan.name} has no matching skill")
        else:
            orphan.unlink()
            print(f"  - {orphan.name} (no matching skill)")

    if args.check:
        if stale or orphans:
            print(f"{len(stale) + len(orphans)} archive(s) out of date, rebuild with: python scripts/build_zips.py", file=sys.stderr)
            return 1
        print(f"archives current ({len(skill_dirs)} checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
