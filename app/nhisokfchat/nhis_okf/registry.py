"""Ground-truth domain knowledge for the NHIS 2023 diabetes slice.

This module is the **data-science skill's knowledge**, encoded as data: for each
variable, what it means, its valid response codes, its survey **universe** (the
skip-pattern that decides who was even asked), and the fact that NHIS estimates are
**weighted**. The verifier consults this registry as an *independent* source of truth
— it does NOT trust the method a concept claims to have used. That independence is what
lets verification catch a concept whose documented method is wrong.

Universe facts below were confirmed empirically against the 2023 Sample Adult
public-use file (adult23.csv), cross-checking who actually has a non-missing answer,
not assumed from the variable name. See `docs/PRODUCT.md` for why the universe matters.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# The mandatory final annual weight for the NHIS Sample Adult file. Unweighted counts
# are simply wrong for population estimates; this is not optional.
SAMPLE_ADULT_WEIGHT = "WTFA_A"

# Complex-survey design variables (Taylor-series linearization for standard errors).
# The lean slice reports weighted point estimates; design-based variance is a
# documented upgrade path (see SKILL.md), so these are recorded but not yet required.
DESIGN_STRATUM = "PSTRAT"
DESIGN_PSU = "PPSU"

# NHIS reserves these numeric codes for non-substantive answers across most items.
# 7 = Refused, 8 = Not Ascertained, 9 = Don't Know. They are never valid analysis values.
#
# REFERENCE ONLY — this constant is NOT applied automatically. Exclusion is enforced
# explicitly per variable via each Variable.valid_codes tuple, because the substantive
# range differs by item (e.g. continuous DIBAGETC_A reserves 96-99, not 7/8/9). When you
# add a variable, set valid_codes deliberately; do not rely on this list as a filter.
NONSUBSTANTIVE_CODES = (7, 8, 9, 77, 88, 99, 97, 98)


@dataclass(frozen=True)
class Variable:
    """Ground truth for one NHIS variable in the diabetes slice."""

    name: str
    label: str
    # The survey universe: the boolean condition (over the dataframe) for who was asked.
    # `None` means "asked of all Sample Adults" (no skip-pattern gate).
    universe_expr: str | None
    # Human-readable statement of that universe, for the OKF concept prose + audit.
    universe_text: str
    # Substantive response codes that count as valid for analysis.
    valid_codes: tuple[int, ...] = ()
    # Codes meaning "yes" when the variable is a yes/no item (for prevalence).
    affirmative_codes: tuple[int, ...] = ()
    weight: str = SAMPLE_ADULT_WEIGHT
    notes: str = ""
    related: tuple[str, ...] = field(default_factory=tuple)


# --- The diabetes slice -----------------------------------------------------------

REGISTRY: dict[str, Variable] = {
    "DIBEV_A": Variable(
        name="DIBEV_A",
        label="Ever told you had diabetes",
        universe_expr=None,  # asked of all sample adults
        universe_text="All sample adults.",
        valid_codes=(1, 2),
        affirmative_codes=(1,),
        notes=(
            "'Diagnosed diabetes' = DIBEV_A == 1, per CDC's published methodology. "
            "Borderline/prediabetes is a separate item (PREDIB_A). Note: no "
            "programmatic GESDIB_A (gestational) filter is applied — CDC does not "
            "exclude gestational-only cases from DIBEV_A == 1, and adding such a "
            "filter would shift the estimate ~0.9pp."
        ),
        related=("DIBINS_A", "DIBPILL_A", "DIBAGETC_A", "PREDIB_A"),
    ),
    "DIBINS_A": Variable(
        name="DIBINS_A",
        label="Currently takes insulin",
        # Empirically confirmed: answered by adults ever told they had diabetes OR
        # told they had prediabetes. NOT the whole sample. The *analytical* universe
        # for "insulin use among people with diagnosed diabetes" is the narrower
        # DIBEV_A == 1 (see analytical_universe below).
        universe_expr="(DIBEV_A == 1) | (PREDIB_A == 1)",
        universe_text=(
            "Adults ever told they had diabetes (DIBEV_A == 1) or prediabetes "
            "(PREDIB_A == 1). The clinically meaningful 'among diagnosed diabetics' "
            "denominator is the narrower DIBEV_A == 1."
        ),
        valid_codes=(1, 2),
        affirmative_codes=(1,),
        notes=(
            "Two traps: (1) computing over the whole sample inflates nothing but "
            "deflates the rate massively because most adults were never asked; "
            "(2) using the full *question* universe (incl. prediabetics) understates "
            "insulin use among actual diabetics. Both are wrong for the headline claim."
        ),
        related=("DIBEV_A", "DIBPILL_A"),
    ),
    "DIBPILL_A": Variable(
        name="DIBPILL_A",
        label="Currently takes diabetic pills",
        universe_expr="(DIBEV_A == 1) | (PREDIB_A == 1)",
        universe_text=(
            "Adults ever told they had diabetes (DIBEV_A == 1) or prediabetes "
            "(PREDIB_A == 1)."
        ),
        valid_codes=(1, 2),
        affirmative_codes=(1,),
        related=("DIBEV_A", "DIBINS_A"),
    ),
    "DIBAGETC_A": Variable(
        name="DIBAGETC_A",
        label="Age first told had diabetes (top-coded)",
        universe_expr="DIBEV_A == 1",
        universe_text="Adults ever told they had diabetes (DIBEV_A == 1).",
        # Continuous age; substantive values are < 96. 96/97/98/99 are reserved.
        valid_codes=tuple(range(0, 96)),
        notes="Top-coded at 85. Values >= 96 are non-substantive and must be dropped.",
        related=("DIBEV_A",),
    ),
    "PREDIB_A": Variable(
        name="PREDIB_A",
        label="Ever told you had prediabetes",
        universe_expr=None,
        universe_text="All sample adults.",
        valid_codes=(1, 2),
        affirmative_codes=(1,),
        related=("DIBEV_A",),
    ),
    # --- Hypertension (a second condition; same engine, no changes) ----------------
    "HYPEV_A": Variable(
        name="HYPEV_A",
        label="Ever told you had high blood pressure",
        universe_expr=None,  # asked of all sample adults
        universe_text="All sample adults.",
        valid_codes=(1, 2),
        affirmative_codes=(1,),
        notes="'Diagnosed hypertension' = HYPEV_A == 1.",
        related=("HYPMED_A",),
    ),
    "HYPMED_A": Variable(
        name="HYPMED_A",
        label="Currently takes blood-pressure medication",
        # Clean skip-pattern: asked only of adults ever told they had hypertension.
        universe_expr="HYPEV_A == 1",
        universe_text="Adults ever told they had high blood pressure (HYPEV_A == 1).",
        valid_codes=(1, 2),
        affirmative_codes=(1,),
        notes=(
            "Asked only of HYPEV_A == 1. A whole-sample rate is badly deflated (most "
            "adults were never asked); the claim is among adults with hypertension."
        ),
        related=("HYPEV_A",),
    ),
    # --- Body measures (whole-sample continuous; same weighted-mean engine) ---------
    # Confirmed empirically against adult23.csv: both are asked of ALL sample adults
    # (n=29,522, no skip-pattern), so universe is None. Weight is WTFA_A. The top-codes
    # (996-999 lbs / 96-99 in) are non-substantive and must be dropped before any mean.
    "WEIGHTLBTC_A": Variable(
        name="WEIGHTLBTC_A",
        label="Weight without shoes (pounds, top-coded)",
        universe_expr=None,  # asked of all sample adults
        universe_text="All sample adults.",
        # Substantive weights are 100-299 (299 = top-code). 996-999 are non-substantive
        # (996 = not on file / not ascertained, 997 refused, 999 don't know).
        valid_codes=tuple(range(100, 300)),
        notes="Top-coded at 299 lbs. Codes 996-999 are non-substantive and must be dropped.",
        related=("HEIGHTTC_A", "BMICAT_A"),
    ),
    "HEIGHTTC_A": Variable(
        name="HEIGHTTC_A",
        label="Height without shoes (inches, top-coded)",
        universe_expr=None,  # asked of all sample adults
        universe_text="All sample adults.",
        # Substantive heights are 59-76 in. 96-99 are non-substantive.
        valid_codes=tuple(range(59, 77)),
        notes="Codes 96-99 are non-substantive and must be dropped.",
        related=("WEIGHTLBTC_A", "BMICAT_A"),
    ),
}


def get(name: str) -> Variable:
    if name not in REGISTRY:
        raise KeyError(
            f"{name!r} is not in the registry. Known variables: {sorted(REGISTRY)}"
        )
    return REGISTRY[name]


# --- Cross-year resolution (the 2019 redesign rename) --------------------------------
#
# The 2019 NHIS redesign renamed and recoded variables. A longitudinal trend that joins
# years by a single variable name silently breaks, because the name does not exist in the
# other year. This map is the ground truth the trend verifier uses to resolve each year
# correctly — and to detect a naive single-name join.
#
# canonical -> {year: (variable, weight, valid_codes, affirmative_codes, encoding)}
#
# `encoding` describes each year's substantive value domain — "categorical" (a small set of
# codes, e.g. 1/2/3) or "continuous" (a wide numeric range) — so the trend verifier can
# refuse a join across incompatible encodings. It is a hint; the guard confirms the domain
# empirically against the real data rather than trusting this label.
#
# Borderline/prediabetes handling: 2018 DIBEV1 carries borderline as code 3 *within* the
# variable; 2023 splits prediabetes into a separate item (PREDIB_A) and DIBEV_A is 1/2. For
# a comparable "diagnosed diabetes" denominator, 2018 counts borderline (3) as not-diagnosed
# (denominator 1/2/3, numerator 1), matching how 2023 treats prediabetics as DIBEV_A == 2.
CROSS_YEAR: dict[
    str, dict[int, tuple[str, str, tuple[int, ...], tuple[int, ...], str]]
] = {
    "diabetes_ever": {
        2018: ("DIBEV1", "WTFA_SA", (1, 2, 3), (1,), "categorical"),
        2023: ("DIBEV_A", "WTFA_A", (1, 2), (1,), "categorical"),
    },
    # The 2019 redesign silently RECODED body-mass index: 2018 BMI is a continuous value
    # stored x100 (integer 2814 = BMI 28.1; substantive band ~1000-9998, 9999 reserved),
    # while 2023 BMICAT_A is a 1-4 category. Nothing is absent, so the rename-gap check
    # passes — but the encodings are incompatible and no mean-BMI trend is comparable.
    "bmi": {
        2018: ("BMI", "WTFA_SA", tuple(range(1000, 9999)), (), "continuous"),
        2023: ("BMICAT_A", "WTFA_A", (1, 2, 3, 4), (), "categorical"),
    },
}

# Per-year Sample Adult public-use CSV filenames (under data/).
YEAR_FILES: dict[int, str] = {2018: "samadult.csv", 2023: "adult23.csv"}
YEAR_CSV_ZIP: dict[int, str] = {
    2018: "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Datasets/NHIS/2018/samadultcsv.zip",
    2023: "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Datasets/NHIS/2023/adult23csv.zip",
}


# The *analytical* universe for the headline insulin claim. Distinct from the question
# universe in the registry: the claim is about people with diagnosed diabetes, so the
# denominator is DIBEV_A == 1 — not the whole sample, and not the prediabetes-inclusive
# question universe. The verifier uses this when checking the canonical claim.
ANALYTICAL_UNIVERSES: dict[str, str] = {
    "DIBINS_A__among_diagnosed": "DIBEV_A == 1",
    "DIBPILL_A__among_diagnosed": "DIBEV_A == 1",
    "HYPMED_A__among_diagnosed": "HYPEV_A == 1",
}
