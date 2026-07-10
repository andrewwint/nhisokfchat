---
type: variable_definition
title: "Weight without shoes (pounds, top-coded)"
description: "Weighted mean weight of U.S. adults, 2023"
resource: "https://www.cdc.gov/nchs/nhis/2023nhis.htm"
tags: [nhis-2023, diabetes, WEIGHTLBTC_A, mean]
timestamp: "2026-07-10T00:16:06Z"
# extension keys (OKF consumers tolerate unknown fields)
id: WEIGHTLBTC_A
variable: WEIGHTLBTC_A
question_universe: "All sample adults."
weight: WTFA_A
source: "NHIS 2023 Sample Adult public-use file (adult23.csv)"
statistic: "Weighted mean weight of U.S. adults, 2023"
kind: mean
value: 178.53
unit: "lbs"
verification:
  verdict: PASS
  method: execution-grounded
  correct_pct: 178.53
  claimed_pct: 178.53
  delta_pp: 0.0
  detail: "178.53 (95% CI 177.89-179.17; design-based SE 0.33)"
  verified_at: 2026-07-10T00:16:06Z
---

# Weight without shoes (pounds, top-coded)

WEIGHTLBTC_A is self-reported weight without shoes in pounds, asked of all sample adults
and top-coded at 299. Codes 996-999 are non-substantive (not ascertained / refused / don't
know) and must be dropped before any weight analysis — leaving them in treats them as
~1000-pound observations and badly inflates the mean. Any mean over this variable must be
survey-weighted (WTFA_A) over the whole adult sample.

The headline claim is the survey-weighted mean weight of U.S. adults in 2023. Dropping the
996-999 codes and applying the survey weights are both required: skipping either shifts the
number in a way execution catches. Related body measure: [HEIGHTTC_A](./HEIGHTTC_A.md).

## Verified statistic

**Weighted mean weight of U.S. adults, 2023: 178.53 lbs**

- Basis: 178.53 (95% CI 177.89-179.17; design-based SE 0.33)
- Verification: executed against NHIS 2023 Sample Adult public-use file (adult23.csv); verdict **PASS**.

## Reproduce

Weighted, verified figure (aggregate only — the number to cite):

```bash
nhis analyze --variable WEIGHTLBTC_A --stat mean
```

Raw row inspection (unweighted, not verified — for sanity-checking only; see the [tool reference](../references/parquet_query.md)):

```bash
nhis rows --columns "WEIGHTLBTC_A" --limit 10
```

## Related
- [HEIGHTTC_A](./HEIGHTTC_A.md)
