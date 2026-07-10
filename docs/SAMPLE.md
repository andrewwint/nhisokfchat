# Sample queries — the grounded chat agent (the end-user surface)

**The chat agent is the only end-user surface.** End users ask questions in natural language;
they never touch the CLI. The agent runs on **Amazon Bedrock AgentCore** when deployed
(`agentcore invoke`). It has **two deterministic, aggregate-only tools and no other window onto
the data**:

- `tool_search_okf` — retrieval over the verified OKF bundle (grounded at *compile* time):
  answers from a precomputed concept, cites the concept id, quotes the figure + design-based CI.
- `tool_analyze_rows` — a deterministic, survey-weighted computation with a design-based
  CI for an *ad-hoc subgroup* a concept does not already carry (grounded at *query* time):
  verified variables only, aggregate-only, and it refuses rather than guesses. Its
  agent-supplied `universe` filter passes an allow-list validator (`COLUMN <op> NUMBER` joined
  by `& | ( )` over known columns) before any `df.eval`, so the injection sink is closed.

The agent states the universe + weight basis with every figure and never invents a number, and
it never returns individual survey records — there is **no raw-row tool** in the deploy. `nhis
analyze` / `nhis rows` (further down) are **internal researcher tools in the lab repo**, not the
deployed surface. Sections 1–4 are **real `agentcore invoke` responses**, captured live from the
deployed AgentCore runtime (`nhisokfchat`, us-east-1, `mode: generative`) and then torn down.

## 1. A verified figure

```
$ agentcore invoke --prompt "What share of U.S. adults with diagnosed diabetes take insulin?"
```
> Based on the verified OKF bundle, here is the finding:
>
> **Approximately 32.0% of U.S. adults with diagnosed diabetes currently take insulin.**
> Specifically, the survey-weighted estimate is **31.96%** (95% CI: 30.08%–33.84%) **[DIBINS_A]**.
> - **Universe/denominator:** U.S. adults ever told by a doctor they have diabetes, survey-weighted.
> - **Survey year:** 2023 NHIS. **Design-based SE** 0.96pp, **DEFF** 1.39.
>
> *This is a public, aggregate survey statistic and is not medical advice.*

*(Real `mode: generative` response — Bedrock AgentCore, Claude Sonnet over the verified bundle.
The not-medical-advice / aggregate-only safety framing is appended to every answer.)*

## 2. Refusal — no concept in the bundle

```
$ agentcore invoke '{"question": "What is the prevalence of asthma among U.S. adults?"}'
```
> I'm sorry, but I **cannot answer this question** from the verified data bundle. The verified
> bundle currently contains only the following concepts:
> - **Diagnosed diabetes** (ever told) [DIBEV_A]
> - **Prediabetes** (ever told) [PREDIB_A]
> - **Insulin use** among adults with diagnosed diabetes [DIBINS_A]
> - **Age at diabetes diagnosis** [DIBAGETC_A]
>
> There is no asthma concept, and I don't invent numbers. For authoritative asthma statistics,
> consult CDC's NCHS.

*(Real `mode: generative` response, live from the deployed runtime. The agent refuses cleanly
rather than serving a nearby concept, and truthfully lists what it *does* have.)*

## 3. Grounded — and honest about its boundary

```
$ agentcore invoke '{"question": "how does survey weighting change diabetes prevalence?"}'
```
> The survey-weighted prevalence of diagnosed diabetes among U.S. adults in 2023 is **9.8%**
> (95% CI 9.39–10.20) **[DIBEV_A]**, with a design effect (DEFF) of **1.41** … However, I
> cannot provide the specific difference between weighted and unweighted prevalence from the
> verified bundle, as those comparative figures are not returned by the search.

## 4. An ad-hoc subgroup — answered at query time (the second tool)

No concept pre-computes insulin use *among women specifically*, so the agent calls
`tool_analyze_rows`, which runs the same deterministic, weights-mandatory computation the
verifier uses — restricted to the verified `DIBINS_A` — and reports the aggregate + CI:

```
$ agentcore invoke '{"question": "Among adults with diagnosed diabetes, what share of women take insulin?"}'
```
> Among **adult women with diagnosed diabetes**, an estimated **31.9% currently take insulin**
> (95% CI: 29.2%–34.6%), based on a survey-weighted analysis of the verified variable
> **[DIBINS_A]**.
> - **Universe/denominator:** U.S. adult women with diagnosed diabetes (`DIBEV_A == 1 & SEX_A == 2`)
> - Survey-weighted by `WTFA_A`, with a design-based CI; unweighted n = 1,712.

That **31.88%** is not an LLM guess — it is `tool_analyze_rows` computing over
`DIBEV_A == 1 & SEX_A == 2`, weighted by `WTFA_A`, with a design-based CI. Asked for an
**unverified** variable, the same tool refuses:

```
$ agentcore invoke '{"question": "What share of U.S. adults currently smoke cigarettes?"}'
```
> I'm sorry, but I **cannot answer this question** from the verified data bundle. Both tools
> returned no usable result: the OKF bundle has no precomputed smoking concept, and the
> microdata variable for smoking status (`SMKCIGST_A`) is **not among the verified variables**.
> I cannot invent, estimate, or guess a figure.

## Why this matters

Asked the same weighting question, a frontier chat model with no grounding confidently
produced an unweighted **11.2%** figure, race/age subgroup tables, and a fabricated claim
about this project's internals — none of it verified here. The grounded agent **refused to
state the unweighted number** — even though 11.2% is a real value we computed — purely because
it is not a verified concept in the bundle.

Grounding makes the agent *less* willing to guess than a strong ungrounded model. That is the
point: every figure it serves passed execution-grounded verification, and it would rather
refuse than fabricate.

---

# Internal / researcher tool — `nhis analyze` (ad-hoc subpopulation lookups)

`nhis analyze` is an **internal researcher CLI, not the end-user surface** — it is the same
deterministic engine the chat's `tool_analyze_rows` tool wraps (section 4), exposed on the
command line for direct inspection. You filter across rows with an arbitrary universe
expression (the *means*); the command returns only a **weighted aggregate with its
design-based 95% CI** (the *output*). It never emits individual records — the aggregate-only
safety scope, enforced in code — and it is **grounded-or-refuse**: it answers only for a
variable backed by a verified concept in the compiled bundle. (`nhis rows`, further, is the
one raw-row researcher tool — also internal, loudly caveated, and never reachable from the
chat agent.)

```bash
nhis analyze --variable <VAR> --universe "<pandas expr>" --stat prevalence|mean|quantile [--q 0.5]
```

All figures below are real output against the CDC NHIS 2023 public-use file.

## Prevalence within a subpopulation

Insulin use **among adults with diagnosed diabetes** (`DIBEV_A == 1`):

```
$ nhis analyze --variable DIBINS_A --universe "DIBEV_A == 1" --stat prevalence
DIBINS_A prevalence: 31.96% (95% CI 30.08-33.84%; design-based SE 0.96; weighted by WTFA_A;
  universe: DIBEV_A == 1; n=3291 unweighted, denominator 25,248,324 weighted)
```

### The universe changes the number

Widening the same insulin question to **diabetes _or_ prediabetes** roughly halves the
rate — prediabetics rarely use insulin. This is why the universe is stated with every
figure:

```
$ nhis analyze --variable DIBINS_A --universe "(DIBEV_A == 1) | (PREDIB_A == 1)" --stat prevalence
DIBINS_A prevalence: 16.75% (95% CI 15.66-17.84%; design-based SE 0.56; weighted by WTFA_A;
  universe: (DIBEV_A == 1) | (PREDIB_A == 1); n=6324 unweighted, denominator 49,736,586 weighted)
```

## Weighted mean and quantile (continuous variables)

Mean and median **age first told had diabetes** among diagnosed adults (non-substantive
codes 96–99 dropped, survey-weighted):

```
$ nhis analyze --variable DIBAGETC_A --universe "DIBEV_A == 1" --stat mean
DIBAGETC_A mean: 47.41 (95% CI 46.75-48.08; design-based SE 0.34; weighted by WTFA_A;
  universe: DIBEV_A == 1; n=3170 unweighted, denominator 24,498,399 weighted)

$ nhis analyze --variable DIBAGETC_A --universe "DIBEV_A == 1" --stat quantile --q 0.5
DIBAGETC_A quantile (q=0.5): 50.00 (95% CI 48.00-50.00; design-based SE 0.01; weighted by
  WTFA_A; universe: DIBEV_A == 1; n=3170 unweighted, denominator 24,498,399 weighted)
```

## Sex-stratified subpopulation

The same query surface stratifies by any loaded column with **no engine change** — here
insulin use among adults with diagnosed diabetes (`DIBEV_A == 1`) split by sex (`SEX_A`:
1 = male, 2 = female). Each call returns an aggregate estimate and its design-based CI,
never any individual rows:

```
$ nhis analyze --variable DIBINS_A --universe "DIBEV_A == 1 & SEX_A == 1" --stat prevalence
DIBINS_A prevalence: 32.04% (95% CI 29.22-34.85%; design-based SE 1.44; weighted by WTFA_A;
  universe: DIBEV_A == 1 & SEX_A == 1; n=1579 unweighted, denominator 12,631,912 weighted)

$ nhis analyze --variable DIBINS_A --universe "DIBEV_A == 1 & SEX_A == 2" --stat prevalence
DIBINS_A prevalence: 31.88% (95% CI 29.21-34.56%; design-based SE 1.36; weighted by WTFA_A;
  universe: DIBEV_A == 1 & SEX_A == 2; n=1712 unweighted, denominator 12,616,413 weighted)
```

## By-group table in one call (`--groupby`)

`--groupby <COL>` returns the whole weighted table in a single deterministic call — one
aggregate cell (estimate + design-based CI + unweighted n) per substantive value of the
grouping column, so the *table*, not just each cell, is deterministic. Non-substantive
group codes (e.g. `SEX_A` 7/9) are dropped and the group count is capped (a mistaken
groupby on a near-continuous column errors rather than emitting a huge table). Cells are
**aggregates only — never rows**, and each equals the matching single `nhis analyze` cell.
Here, insulin use among diagnosed adults (`DIBEV_A == 1`) by sex:

```
$ nhis analyze --variable DIBINS_A --universe "DIBEV_A == 1" --groupby SEX_A --stat prevalence
DIBINS_A prevalence by SEX_A (survey-weighted by WTFA_A; universe: DIBEV_A == 1):
  SEX_A=1: 32.04% (95% CI 29.22-34.85%; n=1579)
  SEX_A=2: 31.88% (95% CI 29.21-34.56%; n=1712)
```

The by-group table above is an **internal researcher (`nhis analyze`) capability in the lab
repo**. The deployed chat agent does not ship a `groupby_table` tool; for a "by <group>"
question it calls `tool_analyze_rows` once per group value (verified-variable-or-refuse,
aggregate only).

## Refusals (grounded-or-refuse, and no fabricated numbers)

A variable with no verified concept is refused, and the message lists what is available:

```
$ nhis analyze --variable AGE_A --universe "DIBEV_A == 1" --stat mean
refused: 'AGE_A' is not backed by a verified concept in the compiled bundle. Run
  `nhis compile` first, or choose one of: DIBAGETC_A, DIBEV_A, DIBINS_A, PREDIB_A.
```

An empty subpopulation refuses rather than reporting a confidently-wrong `0.0`:

```
$ nhis analyze --variable DIBAGETC_A --universe "DIBEV_A == 999" --stat mean
could not compute: empty subpopulation: universe 'DIBEV_A == 999' matches no substantive
  DIBAGETC_A rows — no weighted estimate is defined
```

Every estimate is weighted by `WTFA_A` with a design-based CI (Taylor linearization for
proportions/means; Woodruff for quantiles) using the `PSTRAT`/`PPSU` design variables.
