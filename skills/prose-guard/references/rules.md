# Prose rules

The conventions prose-guard enforces. Other skills link here rather than restating them.

These apply to every piece of English a session produces: READMEs, docs, `CLAUDE.md`, commit messages, PR bodies, issue text, code comments meant for humans.

They do not apply to quoted source material, third-party text, or a file the user has said is stored verbatim.

## Hard rules

**No em dashes.** Use a comma, a colon, a period, or parentheses. The em dash is the single loudest tell that a machine wrote the sentence.

- Bad: `The engine decides, the model justifies — that split is the whole design.`
- Good: `The engine decides and the model justifies. That split is the whole design.`

**No AI tells.** The vocabulary listed in `references/tells.md` reads as generated text regardless of whether it is accurate. Replace with a plain word or delete the sentence.

**No filler openers or closers.** Cut `In today's world`, `It's worth noting that`, `In conclusion`, `Let's dive in`, `At the end of the day`. Start with the claim.

**No hedge stacking.** One hedge per sentence at most. `This might potentially cause some issues in certain cases` says nothing. Either it causes the issue or you do not know yet, so say which.

**No bullet bloat.** Bullets are for genuinely parallel items. If a bullet runs past about forty words it is a paragraph and should be written as one. If a list runs past about eight items it is a table or a section.

**No inflated contrast.** The `it isn't just X, it's Y` pattern, and its cousin `not only X but also Y`, are padding. Say Y.

## Soft rules

Prefer the shorter word. `use` over `utilize`, `to` over `in order to`, `about` over `regarding`, `so` over `accordingly`.

Prefer the concrete number. "much faster" is worth less than "about 4x faster on the 31-POD bench".

Keep sentences under roughly forty words. Long sentences are usually two sentences with a comma splice in between.

Write claims, not vibes. If a sentence would survive being deleted, delete it.

## Words that are fine in context

Technical terms are not tells when they carry technical meaning. `robust` in a statistics or optimization context, `convergence`, `curated` for hand-built data, `state of the art` in a paper's related-work section. The linter marks these `medium` rather than `high` for exactly this reason. Judge them, do not reflex-delete them.

## Suppression

To turn the linter off for a stretch of a file:

```
<!-- prose-lint: off -->
... text the rules should not touch ...
<!-- prose-lint: on -->
```

Code fences, inline code, URLs, and HTML comments are already skipped.
