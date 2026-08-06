# claude-workflow-skills

Skills I use with [Claude Code](https://claude.com/claude-code). They exist to cut token spend without losing output quality.

Three ideas run through all of them:

1. If a check can be a script, it is a script. A linter returns six lines. Reading three files to eyeball the same thing costs thousands of tokens and still misses cases.
2. `SKILL.md` is a router, not a manual. Detail sits in `references/` and loads only when a branch is actually taken.
3. Every skill description stays in context for the whole session, so there are few skills here and each one has to earn that space.

## Skills

| Skill | What it does |
| --- | --- |
| [repo-scout](skills/repo-scout) | Maps an unfamiliar repo in one pass so you can skip the exploratory reads. |
| [agent-contract](skills/agent-contract) | Writes and audits the contract future sessions start from, and catches it going stale. |
| [docs-sync](skills/docs-sync) | Works out which docs a code change made stale, then opens only those. |
| [prose-guard](skills/prose-guard) | Keeps writing free of em dashes, AI tells, and bullet bloat. Detection runs as a script. |
| [readme-brand](skills/readme-brand) | The README house style, plus a checker for links, images, and heading anchors. |
| [llm-pipeline](skills/llm-pipeline) | Architecture rules for code that calls a model, plus an audit for leaked keys. |
| [llm-evals](skills/llm-evals) | Mock and live eval lanes, versioned thresholds, and a gate that fails on regressions. |
| [claim-trace](skills/claim-trace) | Checks every number in a paper against the run artifacts it should have come from. |
| [session-handoff](skills/session-handoff) | Writes a short state file so the next session starts cold and cheap. |

## Install

```bash
python install.py
```

That copies each skill into `~/.claude/skills/`. Add `--dry-run` to see what it would touch, or `--force` to overwrite a skill you already have.

Prebuilt zips for the Claude app (Settings > Capabilities > Skills) live in `zips/`.

## Layout

```
skills/<name>/
  SKILL.md       the router, kept short
  references/    loaded on demand
  scripts/       stdlib Python, no install step
  assets/        templates copied into your repo
```

Skills that need each other link as siblings, so the same relative path works in the repo and in `~/.claude/skills/`.
