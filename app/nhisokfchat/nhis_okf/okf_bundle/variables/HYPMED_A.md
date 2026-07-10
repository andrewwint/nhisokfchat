---
type: variable_definition
title: "Takes blood-pressure medication (among adults with hypertension)"
description: "Weighted % currently taking blood-pressure medication among U.S. adults with diagnosed hypertension, 2023"
resource: "https://www.cdc.gov/nchs/nhis/2023nhis.htm"
tags: [nhis-2023, diabetes, HYPMED_A, prevalence]
timestamp: "2026-07-10T00:16:06Z"
# extension keys (OKF consumers tolerate unknown fields)
id: HYPMED_A
variable: HYPMED_A
question_universe: "Adults ever told they had high blood pressure (HYPEV_A == 1)."
analytical_universe: "HYPEV_A == 1"
weight: WTFA_A
source: "NHIS 2023 Sample Adult public-use file (adult23.csv)"
statistic: "Weighted % currently taking blood-pressure medication among U.S. adults with diagnosed hypertension, 2023"
value_pct: 79.62
verification:
  verdict: PASS
  method: execution-grounded
  correct_pct: 79.62
  claimed_pct: 79.62
  delta_pp: 0.0
  detail: "79.62% (95% CI 78.63-80.61; design-based SE 0.50pp, DEFF 1.74)"
  ci_95: [78.63, 80.61]
  se_pp: 0.50
  deff: 1.74
  variance_method: taylor-linearization (design-based)
  verified_at: 2026-07-10T00:16:06Z
---

# Takes blood-pressure medication (among adults with hypertension)

HYPMED_A records whether an adult currently takes medication for high blood pressure. It is
a skip-pattern item, asked only of adults ever told they had hypertension ([HYPEV_A](./HYPEV_A.md) ==
1). The headline claim is medication use **among people with diagnosed hypertension**, so
the denominator is HYPEV_A == 1, survey-weighted — not the whole sample.

## Verified statistic

**Weighted % currently taking blood-pressure medication among U.S. adults with diagnosed hypertension, 2023: 79.62%**

- 95% CI: [78.63, 80.61] (design-based, Taylor linearization; SE 0.50pp; DEFF 1.74)
- Basis: 79.62% (95% CI 78.63-80.61; design-based SE 0.50pp, DEFF 1.74)
- Verification: executed against NHIS 2023 Sample Adult public-use file (adult23.csv); verdict **PASS**.

## Reproduce

Weighted, verified figure (aggregate only — the number to cite):

```bash
nhis analyze --variable HYPMED_A --universe "HYPEV_A == 1"
```

Raw row inspection (unweighted, not verified — for sanity-checking only; see the [tool reference](../references/parquet_query.md)):

```bash
nhis rows --columns "HYPEV_A,HYPMED_A" --universe "HYPEV_A == 1" --limit 10
```

## Related
- [HYPEV_A](./HYPEV_A.md)
