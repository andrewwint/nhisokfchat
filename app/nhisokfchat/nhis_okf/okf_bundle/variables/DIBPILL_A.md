---
type: variable_definition
title: "Takes diabetic pills (among adults with diagnosed diabetes)"
description: "DIBPILL_A records whether an adult currently takes diabetic pills (oral medication)."
resource: "https://www.cdc.gov/nchs/nhis/2023nhis.htm"
tags: [nhis-2023, diabetes, DIBPILL_A]
timestamp: "2026-07-10T00:16:06Z"
# extension keys (OKF consumers tolerate unknown fields)
id: DIBPILL_A
variable: DIBPILL_A
question_universe: "Adults ever told they had diabetes (DIBEV_A == 1) or prediabetes (PREDIB_A == 1)."
analytical_universe: "DIBEV_A == 1"
weight: WTFA_A
source: "NHIS 2023 Sample Adult public-use file (adult23.csv)"
verification:
  verdict: DESCRIPTIVE
  method: execution-grounded
  verified_at: 2026-07-10T00:16:06Z
---

# Takes diabetic pills (among adults with diagnosed diabetes)

DIBPILL_A records whether an adult currently takes diabetic pills (oral medication). Like
the insulin item ([DIBINS_A](./DIBINS_A.md)), it is a skip-pattern question asked of adults with
diabetes or prediabetes, so any "share on pills" claim must use the analytical universe
DIBEV_A == 1 (adults with diagnosed diabetes), survey-weighted — not the whole sample.

## Related
- [DIBEV_A](./DIBEV_A.md)
- [DIBINS_A](./DIBINS_A.md)
