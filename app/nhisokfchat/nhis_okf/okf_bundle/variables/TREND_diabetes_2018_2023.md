---
type: metric
title: "Diagnosed diabetes prevalence, 2018 vs 2023"
description: "Weighted prevalence of diagnosed diabetes among U.S. adults, 2018 vs 2023"
resource: "https://www.cdc.gov/nchs/nhis/2023nhis.htm"
tags: [nhis, diabetes, trend, 2018, 2023]
timestamp: "2026-07-10T00:16:06Z"
# extension keys (OKF consumers tolerate unknown fields)
id: TREND_diabetes_2018_2023
canonical: diabetes_ever
years: [2018, 2023]
method: per-year-variable (rename-aware across the 2019 redesign)
values_pct: {2018: 10.09, 2023: 9.8}
verification:
  verdict: PASS
  method: execution-grounded (cross-year)
  correct_pct: {2018: 10.09, 2023: 9.8}
  verified_at: 2026-07-10T00:16:06Z
links: [DIBEV_A]
---

# Diagnosed diabetes prevalence, 2018 vs 2023

Weighted prevalence of diagnosed diabetes among U.S. adults, compared across the 2019 NHIS
redesign. The variable was renamed: `DIBEV1` (2018, weight `WTFA_SA`) became `DIBEV_A`
(2023, weight `WTFA_A`). For comparability, 2018 borderline diabetes (`DIBEV1 == 3`) is
counted as not-diagnosed, matching 2023's split of prediabetes into a separate item.

A correct trend resolves each year to its own variable and weight; it does not join the two
years by a single variable name.

## Verified trend

- 2018: 10.09%
- 2023: 9.8%

- Verification: each year executed against its own file with its own weight; verdict **PASS**.

## Related
- [DIBEV_A](./DIBEV_A.md)
