# CLAUDE.md format

The section order below is the house format. Skip any section the repo does not need, keep the order for the ones it does.

## 1. Header

```markdown
# CLAUDE.md

Orientation for agents working in <name>. Read this before making changes.
**Last verified: YYYY-MM-DD.**
```

The date is load-bearing. `verify_claude_md.py` compares it against the last commit and reports the drift.

## 2. What this project is

Two or three paragraphs. The test for what belongs here: could a session derive this by reading the code? If yes, cut it.

What passes the test: who the user is, what the product refuses to do and why, the constraint that shaped the design, the non-negotiable framing.

What fails: the tech stack list, the directory names, what the functions do.

## 3. Vocabulary

A table, only when the domain has terms a newcomer would guess wrong or that the code uses in a specific sense.

```markdown
| Term | Meaning |
| --- | --- |
| **POD** | Point of Divergence: the moment history splits |
```

Domain jargon that appears in identifiers earns a row. General programming terms do not.

## 4. Architecture map

An annotated tree, not a full listing. Annotate what each path is for, and go only as deep as the reader needs to find things.

```markdown
lib/
  acmg.ts        criteria specs, points, thresholds, classify()
  pipeline.ts    orchestrator, emits stage events, fixture fallback
```

Stop at the file that owns a concept. Listing every file is what `repo-scout` is for, and a hand-maintained listing goes stale within a week.

## 5. Authoritative versus archived

Only when several directories look like plausible places to work. This section prevents the single most expensive mistake, which is editing the superseded generation.

```markdown
| Path | Status | Notes |
| --- | --- | --- |
| `v4/` | **CURRENT, work here** | The complete generation |
| `archive/` | **Frozen** | Superseded. Do not extend |
```

State the default explicitly: when asked to change "the code", which directory is meant.

## 6. Conventions

The rules a session would otherwise violate, each with its consequence. A convention with no stated reason gets overridden the first time it is inconvenient.

Cover writing style, what must never be edited, what must stay in sync with what, and the naming or versioning scheme if there is one.

When a rule exists because something went wrong before, say so and date it. That is the sentence that makes it stick.

## 7. Commands

Only the ones a session will actually run: install, dev, test, lint, build, and any repo-specific script.

`verify_claude_md.py` cross-checks these against `package.json` scripts and `Makefile` targets, so a renamed script gets caught.

## 8. Gotchas

Anything that has cost time and would cost it again. An expected test failure, a service that must be running, an environment variable with a non-obvious value, an approach already tried and rejected.

## Keeping it under the ceiling

Target under 200 lines. When a section outgrows it, move the body into `docs/` and leave a pointer:

```markdown
Scoring and thresholds: see [docs/METHODOLOGY.md](docs/METHODOLOGY.md).
```

Deep methodology, deploy and environment setup, and API detail are the three that should almost always live in `docs/`. The contract routes, the docs contain.
