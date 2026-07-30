<!-- prose-lint: off -->
<!-- This file is a catalog of the flagged vocabulary, so it quotes every tell by design. -->

# AI tells and what to write instead

Load this when the linter fires and the fix is not obvious. The linter has the full pattern list, this file has the reasoning and the replacements.

## Why these words get flagged

Generated text converges on a narrow band of vocabulary: words that sound evaluative without committing to a claim. `seamless`, `powerful`, `comprehensive`, and `robust` all assert quality while saying nothing checkable. Readers who see a lot of model output have learned to spot the band, and the writing reads as unedited machine text even when the content is good.

The fix is almost never a synonym. It is a concrete claim or a deletion.

## High severity, replace or delete

| Flagged | Write instead |
| --- | --- |
| delve into | look at, read, or just start |
| it's worth noting that | delete, state the point |
| in today's world | delete |
| when it comes to | for, with, in |
| a testament to | say what it shows |
| plays a crucial role | say what it does |
| unlock the potential | say what becomes possible |
| take it to the next level | say what improves |
| let's dive in / deep dive | delete |
| seamless, seamlessly | say what does not break |
| game changer, cutting edge | name the technique |
| embark on | start |
| meticulous | delete |
| boasts | has |
| paradigm shift | say what changed |
| synergy | delete |
| revolutionize | say what is different |
| empower | say what it lets someone do |
| holistic | delete |
| harness the power of | use |
| utilize | use |
| in conclusion, in summary | delete, the reader can see the end |
| whether you're a X or a Y | delete the whole clause |

## The two structural tells

**"Not only X but also Y"** exists to make one fact feel like two. Say Y, and mention X only if it stands alone.

- Bad: `The linter not only catches em dashes but also flags hedge stacking.`
- Good: `The linter flags em dashes, hedge stacking, and bullet bloat.`

**"It isn't just X, it's Y"** is the same move with more drama. Say Y.

- Bad: `This isn't just a linter, it's a writing discipline.`
- Good: `The linter is how the discipline gets enforced.`

## Medium severity, judge before cutting

These are legitimate in technical writing and decoration everywhere else. The linter marks them medium so you read the line rather than reflex-deleting.

| Word | Keep it when | Cut it when |
| --- | --- | --- |
| robust | statistics, optimization, control, a named robustness result | describing software quality in general |
| comprehensive | the coverage is actually enumerated | a synonym for "good" |
| state of the art | related work, benchmark comparison | product description |
| significantly | statistical significance with a test behind it | meaning "a lot" |
| leverage | financial leverage, the actual noun | as a verb meaning "use" |
| crucial, vital, essential | a dependency that genuinely blocks | emphasis |
| powerful | a specific capability follows | on its own |
| aims to | describing intent that may fail | describing what the code does |
| foster | almost never | as a verb meaning "cause" |

## Hedge stacking

One hedge is honest. Two is evasion.

- Bad: `This might potentially cause issues in some cases.`
- Good: `This fails when the config is missing.` Or, if you truly do not know: `Untested against a missing config.`

The linter fires at two or more hedges in one sentence. When it does, decide which single uncertainty is real and delete the rest.

## Bullet bloat

Bullets promise parallel items of similar weight. They break down two ways.

**A bullet that runs past forty words** is a paragraph wearing a dash. Unwrap it.

**A list past eight items** has stopped being a list. If the items have shared fields, it is a table. If they have sections, they are headings. If neither, the list is doing organizational work that a rewrite should do instead.

## What the linter cannot catch

Read for these yourself after the linter is clean.

Sentences that would survive deletion. Paragraphs that restate the heading. Claims with no number where a number exists. Passive voice hiding who did the thing. A section that exists because the outline said so rather than because a reader needs it.
