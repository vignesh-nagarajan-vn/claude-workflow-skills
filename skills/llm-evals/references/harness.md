# Eval harness detail

## Dataset design

Aim for 30 to 60 cases before worrying about more. Below about 30, a two-point move is indistinguishable from noise. Past a few hundred, you are paying for precision you are not using.

Compose it deliberately:

- **Typical cases**, the ones the product sees daily. Roughly half.
- **Known-hard cases**, ambiguous input, sparse evidence, conflicting sources.
- **Regression cases**, one per bug ever fixed. This is the highest-value category and the one that gets skipped. Every time you fix an output bug, the input that caused it becomes a permanent case.
- **Adversarial cases**, prompt injection in the input, contradictory instructions, requests the product should refuse.

Store expected outputs where a correct answer exists, and grading criteria where it does not. Version the dataset with the code, and treat a case's expected value as a claim that needs a reason when it changes.

## Judges

When there is no exact answer, a model grades the output. Three rules keep this honest.

**Grade against criteria, not vibes.** Give the judge the same rubric a human reviewer would use, one dimension at a time, each with a defined scale. "Rate quality 1 to 10" produces a number with no meaning.

**Judge with a different model than the one being tested**, or at minimum a different prompt lineage. A model grading its own output rates it generously.

**Calibrate the judge before trusting it.** Hand-grade fifteen cases, run the judge on the same fifteen, and compare. If the judge disagrees with you often, fix the judge before reading any results from it. An uncalibrated judge produces confident numbers that measure nothing.

```ts
const Score = z.object({
  dimension: z.enum(['grounded', 'complete', 'follows_format']),
  verdict: z.enum(['pass', 'partial', 'fail']),
  evidence: z.string(),   // quote the span that decided it
})
```

Requiring evidence makes the judge's mistakes visible. A judge that cannot quote the span that justified its verdict is guessing.

## A/B on a change

Run both variants over the same dataset in the same session, and compare paired per-case results rather than aggregate means. Paired comparison controls for case difficulty and needs far fewer samples to show a real difference.

Report how many cases improved, how many regressed, and how many were unchanged. An accuracy move from 0.84 to 0.86 that improved nine cases and broke seven is a different story from one that improved two and broke none.

## Variance

Run the suite twice with no changes and record the spread. That spread is your noise floor, and any change smaller than it is not a result. Write the number down in the eval README, because everyone who reads a result later needs it.

For a metric near the floor, raise the sample count or the temperature discipline rather than arguing about a one-point move.

## Budget capping

The live lane must not be able to run away.

```ts
let spent = 0
for (const testCase of dataset) {
  if (spent > BUDGET_USD) {
    console.warn(`stopped after ${done}/${dataset.length}, budget reached`)
    break
  }
  const result = await run(testCase)
  spent += cost(result.usage)
}
```

Log the partial count loudly. A suite that silently truncates reports a pass over half the dataset, which is worse than failing.

## CI shape

Mock lane on every commit, no key, must stay green. Live lane on a schedule or on demand, key-gated, writes results JSON. Threshold check runs against that JSON and gates the release.

Keep the results file from each live run, timestamped. The baseline comparison needs a previous run to point at, and a history of results files is the only way to see slow drift.
