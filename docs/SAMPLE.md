# Sample queries — the grounded chat agent (the end-user surface)

**The chat agent is the only end-user surface.** End users ask questions in natural language;
they never touch the CLI. The agent runs on **Amazon Bedrock AgentCore** when deployed
(`agentcore invoke`) and on the same code path locally via `nhis query` (Anthropic API). It
has **three deterministic tools and no other window onto the data**:

- `search_verified_okf` — retrieval over the verified OKF bundle (grounded at *compile* time):
  answers from a precomputed concept, cites the concept id, quotes the figure + design-based CI.
- `analyze_subpopulation` — a deterministic, survey-weighted computation with a design-based
  CI for an *ad-hoc subgroup* a concept does not already carry (grounded at *query* time):
  verified variables only, aggregate-only, and it refuses rather than guesses.
- `groupby_table` — a deterministic, survey-weighted **by-group table** (one aggregate cell +
  design-based CI per substantive group value) for a "by <group>" question, e.g. insulin use
  by sex: verified variables only, aggregate cells only (never rows), refuses rather than guesses.

The agent states the universe + weight basis with every figure and never invents a number.
`nhis analyze` / `nhis rows` (further down) are **internal researcher tools**, not the
end-user surface. Sections 1–4 are real agent responses.

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
$ agentcore invoke --prompt "What is the prevalence of asthma among US adults?"
```
> Unfortunately, **I cannot answer this question from the verified bundle.** The verified OKF
> bundle does not contain a precomputed asthma prevalence concept for U.S. adults, and none of
> my tools returned a relevant match. Providing a figure from outside knowledge would violate
> my hard rules against inventing or estimating numbers.
>
> For authoritative asthma prevalence statistics, I'd recommend consulting CDC's NCHS and CDC
> Asthma Data & Surveillance.

*(Real `mode: generative` response. The agent refuses cleanly rather than serving a nearby
concept — grounded-or-refuse, live.)*

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
`analyze_subpopulation`, which runs the same deterministic, weights-mandatory computation the
verifier uses — restricted to the verified `DIBINS_A` — and reports the aggregate + CI. Real
output from `./.venv/bin/nhis query "…"` (the deployed agent runs the identical code path):

```
$ nhis query "Among adults diagnosed with diabetes, what share of women take insulin?"
```
> Among all U.S. adults diagnosed with diabetes, about **32.0%** currently take insulin
> **[DIBINS_A]**. Among **women specifically**, the share is essentially the same at **31.9%**
> (95% CI: 29.2%–34.6%), based on a survey-weighted denominator of approximately 12.6 million
> women with diagnosed diabetes (unweighted n = 1,712).

The 31.88% women's figure is not an LLM guess — it is `analyze_subpopulation` computing over
`DIBEV_A == 1 & SEX_A == 2`, weighted by `WTFA_A`, with a design-based CI. Asked for
an **unverified** variable, the same tool refuses:

```
$ nhis query "What is the survey-weighted prevalence of current smoking among adults over 40?"
```
> I'm unable to answer this from the verified data bundle. The subpopulation analysis was
> refused because the smoking variable is **not among the verified variables** in the compiled
> bundle (verified: DIBAGETC_A, DIBEV_A, DIBINS_A, DIBPILL_A, HEIGHTTC_A, HYPEV_A, HYPMED_A,
> PREDIB_A, WEIGHTLBTC_A). I cannot invent, estimate, or guess a figure.

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
deterministic engine the chat's `analyze_subpopulation` tool wraps (section 4), exposed on the
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

Hypertension-medication use **among adults told they have hypertension** (`HYPEV_A == 1`):

```
$ nhis analyze --variable HYPMED_A --universe "HYPEV_A == 1" --stat prevalence
HYPMED_A prevalence: 79.62% (95% CI 78.63-80.61%; design-based SE 0.50; weighted by WTFA_A;
  universe: HYPEV_A == 1; n=11083 unweighted, denominator 83,085,709 weighted)
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

The same query surface stratifies by any loaded column with **no engine change** — here the
survey-weighted **mean weight** of U.S. adults by sex (`SEX_A`: 1 = male, 2 = female). Each
call returns an aggregate estimate and its design-based CI, never any individual rows:

```
$ nhis analyze --variable WEIGHTLBTC_A --universe "SEX_A == 1" --stat mean
WEIGHTLBTC_A mean: 195.00 (95% CI 194.20-195.81; design-based SE 0.41; weighted by WTFA_A;
  universe: SEX_A == 1; n=12438 unweighted, denominator 115,446,875 weighted)

$ nhis analyze --variable WEIGHTLBTC_A --universe "SEX_A == 2" --stat mean
WEIGHTLBTC_A mean: 162.68 (95% CI 161.90-163.47; design-based SE 0.40; weighted by WTFA_A;
  universe: SEX_A == 2; n=14599 unweighted, denominator 120,035,788 weighted)
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

The grounded chat agent uses the same computation for a "by <group>" question via its
`groupby_table` tool (verified-variable-or-refuse, aggregate table text only).

## Refusals (grounded-or-refuse, and no fabricated numbers)

A variable with no verified concept is refused, and the message lists what is available:

```
$ nhis analyze --variable AGE_A --universe "DIBEV_A == 1" --stat mean
refused: 'AGE_A' is not backed by a verified concept in the compiled bundle. Run
  `nhis compile` first, or choose one of: DIBAGETC_A, DIBEV_A, DIBINS_A, DIBPILL_A,
  HEIGHTTC_A, HYPEV_A, HYPMED_A, PREDIB_A, WEIGHTLBTC_A.
```

An empty subpopulation refuses rather than reporting a confidently-wrong `0.0`:

```
$ nhis analyze --variable DIBAGETC_A --universe "DIBEV_A == 999" --stat mean
could not compute: empty subpopulation: universe 'DIBEV_A == 999' matches no substantive
  DIBAGETC_A rows — no weighted estimate is defined
```

Every estimate is weighted by `WTFA_A` with a design-based CI (Taylor linearization for
proportions/means; Woodruff for quantiles) using the `PSTRAT`/`PPSU` design variables.
