# CLAUDE.md

Agent contract for this repo. Read this first.

## What this repo is

A personal set of Claude Code skills built around one constraint: cut tokens without losing output quality. It is public, so nothing here may contain private facts, credentials, employer names, academic records, or anything else identifying beyond the GitHub handle.

## The rules every skill follows

1. **Deterministic work goes in a script.** If a rule can be checked by a regex, a diff, or a file walk, write `scripts/*.py` and have `SKILL.md` call it. Never ask the model to read files to find what a script can find.
2. **`SKILL.md` is a router.** Target under 100 lines. Branch into `references/*.md` for detail so the reference only enters context when that branch is taken.
3. **The `description` is the budget.** It is loaded in every session forever. Write it for trigger precision and keep it tight. Adding a skill has a permanent cost, so the bar for a new one is high.
4. **Scripts are stdlib Python only.** No `pip install` step, works on Windows and POSIX, invoked as `python <path>`.
5. **Skills state what to grep, not what to read.**

## Layout

```
install.py           copies skills/* into ~/.claude/skills/
skills/<name>/
  SKILL.md           frontmatter (name, description) + router body
  references/        on-demand detail
  scripts/           stdlib Python
  assets/            templates meant to be copied into a target repo
```

## Cross-references

A skill that needs another skill's reference links to it as a sibling, for example `../prose-guard/references/rules.md`. That path resolves the same in this repo and in `~/.claude/skills/` after install, so there is no shared top-level directory and nothing to rewrite at install time.

## Conventions

Prose in this repo follows [prose-guard's rules](skills/prose-guard/references/rules.md). The repo must pass its own linter:

```bash
python skills/prose-guard/scripts/prose_lint.py
```

Run that before calling any doc change done.

## Adding a skill

1. Confirm no shipped skill already covers it.
2. Write the `description` first. If you cannot make it trigger precisely in one sentence, the skill is scoped wrong.
3. Ask what part is deterministic, and put that part in a script before writing any prose.
4. Add a row to the README table.

Last verified: 2026-07-30.
