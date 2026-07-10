# OKF audit log

Compiled from NHIS 2023 Sample Adult public-use file (adult23.csv).
Last run: 2026-07-10T00:16:06Z

Every concept is verified by *executing* its analysis against the real microdata
with proper survey weights — not by checking links. Quarantined concepts failed
that check and were kept out of the trusted bundle.

| concept | verdict | claimed | correct | delta (pp) | note |
| --- | --- | --- | --- | --- | --- |
| DIBAGETC_A | PASS | 47.41 | 47.41 | 0.0 |  |
| DIBAGETC_A__naive | FAIL | 49.29 | 47.41 | 1.88 | QUARANTINED — lint passed, execution caught it: method is UNWEIGHTED; NHIS estimates require survey weights (WTFA_A); claim (49.29) matches the UNWEIGHTED estimate (49.29), not the survey-weighted one (47.41) |
| DIBEV_A | PASS | 9.8 | 9.8 | 0.0 |  |
| DIBEV_A__tightci | FAIL | 9.8 | 9.8 | 0.0 | QUARANTINED — lint passed, execution caught it: claimed 95% CI half-width 0.14pp understates the design-based 0.40pp — it ignores the survey design effect (DEFF 1.41) |
| DIBINS_A | PASS | 31.96 | 31.96 | 0.0 |  |
| DIBINS_A__naive | FAIL | 3.66 | 31.96 | 28.3 | QUARANTINED — lint passed, execution caught it: method is UNWEIGHTED; NHIS estimates require survey weights (WTFA_A); universe is 'whole sample'; correct analytical universe is 'DIBEV_A == 1' |
| DIBPILL_A | DESCRIPTIVE | — | — | — | documented (no executable statistic) |
| HEIGHTTC_A | PASS | 66.82 | 66.82 | 0.0 |  |
| HEIGHTTC_A__rawcodes | FAIL | 69.05 | 66.82 | 2.23 | QUARANTINED — lint passed, execution caught it: claim (69.05) retains non-substantive codes (96, 97, 98, 99); dropping them via the registry valid_codes gives 66.82 |
| HYPEV_A | PASS | 32.26 | 32.26 | 0.0 |  |
| HYPMED_A | PASS | 79.62 | 79.62 | 0.0 |  |
| HYPMED_A__naive | FAIL | 30.98 | 79.62 | 48.64 | QUARANTINED — lint passed, execution caught it: method is UNWEIGHTED; NHIS estimates require survey weights (WTFA_A); universe is 'whole sample'; correct analytical universe is 'HYPEV_A == 1' |
| PREDIB_A | DESCRIPTIVE | — | — | — | documented (no executable statistic) |
| WEIGHTLBTC_A | PASS | 178.53 | 178.53 | 0.0 |  |
| WEIGHTLBTC_A__rawcodes | FAIL | 250.59 | 178.53 | 72.06 | QUARANTINED — lint passed, execution caught it: claim (250.59) retains non-substantive codes (996, 997, 999); dropping them via the registry valid_codes gives 178.53 |

## Cross-year trends (2019 redesign-rename catch)

| trend | verdict | note |
| --- | --- | --- |
| TREND_bmi__naive | FAIL | QUARANTINED — lint passed, execution caught it: scale/units mismatch: 2018 'BMI' is continuous (substantive values 1171-9159, 2034 distinct), 2023 'BMICAT_A' is categorical (substantive values 1-4, 4 distinct). The 2019 redesign recoded this measure across an incompatible encoding, so the join is not comparable and no trend can be published (the correct outcome is refusal, not a computed series). |
| TREND_diabetes_2018_2023 | PASS |  |
| TREND_diabetes__naive | FAIL | QUARANTINED — lint passed, execution caught it: 2018: variable 'DIBEV_A' is not in the data — it was renamed in the 2019 redesign; the correct 2018 variable is 'DIBEV1'. A single-name join drops 2018, producing a broken trend. |
