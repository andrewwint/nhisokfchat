---
type: variable_definition
title: "Height without shoes (inches, top-coded)"
description: "Weighted mean height of U.S. adults, 2023"
resource: "https://www.cdc.gov/nchs/nhis/2023nhis.htm"
tags: [nhis-2023, diabetes, HEIGHTTC_A, mean]
timestamp: "2026-07-10T00:16:06Z"
# extension keys (OKF consumers tolerate unknown fields)
id: HEIGHTTC_A
variable: HEIGHTTC_A
question_universe: "All sample adults."
weight: WTFA_A
source: "NHIS 2023 Sample Adult public-use file (adult23.csv)"
statistic: "Weighted mean height of U.S. adults, 2023"
kind: mean
value: 66.82
unit: "in"
verification:
  verdict: PASS
  method: execution-grounded
  correct_pct: 66.82
  claimed_pct: 66.82
  delta_pp: 0.0
  detail: "66.82 (95% CI 66.75-66.88; design-based SE 0.03)"
  verified_at: 2026-07-10T00:16:06Z
---

# Height without shoes (inches, top-coded)

HEIGHTTC_A is self-reported height without shoes in inches, asked of all sample adults.
Codes 96-99 are non-substantive (not ascertained / refused / don't know) and must be
dropped before any height analysis — leaving them in treats them as ~96-inch observations
and inflates the mean. Any mean over this variable must be survey-weighted (WTFA_A) over the
whole adult sample.

The headline claim is the survey-weighted mean height of U.S. adults in 2023. Dropping the
96-99 codes and applying the survey weights are both required: skipping either shifts the
number in a way execution catches. Related body measure: [WEIGHTLBTC_A](./WEIGHTLBTC_A.md).

## Verified statistic

**Weighted mean height of U.S. adults, 2023: 66.82 in**

- Basis: 66.82 (95% CI 66.75-66.88; design-based SE 0.03)
- Verification: executed against NHIS 2023 Sample Adult public-use file (adult23.csv); verdict **PASS**.

## Reproduce

Weighted, verified figure (aggregate only — the number to cite):

```bash
nhis analyze --variable HEIGHTTC_A --stat mean
```

Raw row inspection (unweighted, not verified — for sanity-checking only; see the [tool reference](../references/parquet_query.md)):

```bash
nhis rows --columns "HEIGHTTC_A" --limit 10
```

## Related
- [WEIGHTLBTC_A](./WEIGHTLBTC_A.md)
