---
type: variable_definition
title: "Ever told you had high blood pressure"
description: "Weighted prevalence of diagnosed hypertension among U.S. adults, 2023"
resource: "https://www.cdc.gov/nchs/nhis/2023nhis.htm"
tags: [nhis-2023, diabetes, HYPEV_A, prevalence]
timestamp: "2026-07-10T00:16:06Z"
# extension keys (OKF consumers tolerate unknown fields)
id: HYPEV_A
variable: HYPEV_A
question_universe: "All sample adults."
weight: WTFA_A
source: "NHIS 2023 Sample Adult public-use file (adult23.csv)"
statistic: "Weighted prevalence of diagnosed hypertension among U.S. adults, 2023"
value_pct: 32.26
verification:
  verdict: PASS
  method: execution-grounded
  correct_pct: 32.26
  claimed_pct: 32.26
  delta_pp: 0.0
  detail: "32.26% (95% CI 31.57-32.94; design-based SE 0.35pp, DEFF 1.64)"
  ci_95: [31.57, 32.94]
  se_pp: 0.35
  deff: 1.64
  variance_method: taylor-linearization (design-based)
  verified_at: 2026-07-10T00:16:06Z
---

# Ever told you had high blood pressure

HYPEV_A records whether a sample adult was ever told by a health professional that they
had high blood pressure (hypertension). "Diagnosed hypertension" is HYPEV_A == 1. The
population estimate must be survey-weighted (WTFA_A); the unweighted sample share does not
estimate the U.S. adult population.

## Verified statistic

**Weighted prevalence of diagnosed hypertension among U.S. adults, 2023: 32.26%**

- 95% CI: [31.57, 32.94] (design-based, Taylor linearization; SE 0.35pp; DEFF 1.64)
- Basis: 32.26% (95% CI 31.57-32.94; design-based SE 0.35pp, DEFF 1.64)
- Verification: executed against NHIS 2023 Sample Adult public-use file (adult23.csv); verdict **PASS**.

## Reproduce

Weighted, verified figure (aggregate only — the number to cite):

```bash
nhis analyze --variable HYPEV_A
```

Raw row inspection (unweighted, not verified — for sanity-checking only; see the [tool reference](../references/parquet_query.md)):

```bash
nhis rows --columns "HYPEV_A" --limit 10
```

## Related
- [HYPMED_A](./HYPMED_A.md)
