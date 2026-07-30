# LLM pipeline patterns

Shapes for the rules in `SKILL.md`. Sketches are TypeScript with Zod, the same structure works with Pydantic.

## Model justifies, code decides

Split the schema so the model can only return evidence, never the conclusion.

```ts
const Verdict = z.object({
  criterion: z.enum(CRITERIA),
  verdict: z.enum(['met', 'not_met', 'unknown']),
  reasoning: z.string().max(600),
})

// The model returns Verdict[]. The label is computed here, never returned.
export function classify(verdicts: Verdict[]): Label {
  const points = verdicts.filter(v => v.verdict === 'met')
    .reduce((sum, v) => sum + POINTS[v.criterion], 0)
  return pointsToLabel(points)
}
```

Why it holds up: the threshold can be retuned without touching a prompt, the arithmetic is unit-testable, and a reviewer can see exactly which evidence produced the label.

## Schema plus bounded repair

```ts
async function structured<T>(schema: z.ZodType<T>, prompt: string, tries = 2): Promise<T> {
  let lastError = ''
  for (let attempt = 0; attempt <= tries; attempt++) {
    const raw = await provider.complete(attempt === 0 ? prompt : `${prompt}\n\nYour previous reply failed validation:\n${lastError}\nReturn only valid JSON.`)
    const parsed = schema.safeParse(extractJson(raw))
    if (parsed.success) return parsed.data
    lastError = parsed.error.issues.map(i => `${i.path.join('.')}: ${i.message}`).join('; ')
  }
  throw new Error(`schema validation failed after ${tries + 1} attempts: ${lastError}`)
}
```

Bound the retries. Log the attempt count, because a rising average is the early signal that a prompt or a schema has drifted.

## Mock provider

One interface, two implementations, chosen by whether a key is present.

```ts
export interface Provider {
  complete(prompt: string, opts?: Opts): Promise<{ text: string; usage: Usage }>
}

export function getProvider(): Provider {
  return process.env.ANTHROPIC_API_KEY ? new LiveProvider() : new MockProvider()
}
```

The mock keys off the template id, returns fixture data shaped like the real schema, and is deterministic. Rules that keep it honest: it returns the same shapes the schema validates, tests run against it by default, and the UI says plainly which mode it is in so a mocked result is never mistaken for a real one.

## Critic pass

A second call that reviews the first. Useful when output correctness matters more than latency.

```ts
const draft = await generate(state)
for (let round = 0; round < MAX_ROUNDS; round++) {
  const issues = await critique(draft, state)
  if (!issues.length) return { draft, status: 'clean' }
  draft = await revise(draft, issues)
}
return { draft, status: 'disputed', issues }   // keep it, mark it, move on
```

Bound the rounds and keep the disputed result rather than looping. A visible "disputed" mark is more useful than an infinite retry, and it costs a known amount.

Run the critic on the cheaper model first. Escalate only what it flags.

## Stage streaming

```ts
for (const stage of STAGES) {
  controller.enqueue(encode({ type: 'stage', name: stage.name, status: 'running' }))
  const result = await stage.run(ctx)
  controller.enqueue(encode({ type: 'stage', name: stage.name, status: 'done' }))
}
controller.enqueue(encode({ type: 'result', payload: final }))
```

NDJSON, one object per line. The client renders stage indicators from the same events, so progress needs no separate mechanism.

## Provenance

Every generated artifact carries how it was made: model id, template id and version, timestamp, and whether it came from the live or mock provider. Without it you cannot tell which outputs came from a prompt you have since changed, and any regression hunt starts from zero.

```ts
type Provenance = {
  model: string
  template: { id: string; version: number }
  createdAt: string
  mode: 'live' | 'mock'
}
```

## Cost control

Order the prompt so the stable part comes first: system rules, then schema, then the variable input. That prefix can be cached across calls, and cache hits cost a fraction of fresh input tokens.

Set `max_tokens` to what the schema needs. A verdict list does not need a 4000-token ceiling.

Log input and output tokens per call and per pipeline run. Cost surprises come from call counts inside loops, not from any single call, and only per-run totals make that visible.
