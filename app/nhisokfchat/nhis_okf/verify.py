"""Execution-grounded verification — the reason this project exists.

Two layers, deliberately separated so the contrast is visible:

* `lint_concept` is the cheap pre-check a script owns: is the markdown there, do the
  links resolve? It knows nothing about statistics and will happily pass a concept whose
  headline number is wrong.

* `verify_concept` *executes*. It recomputes the statistic the registry-correct way
  (true universe + mandatory survey weights) and compares it to the concept's claim. A
  concept can pass the lint and fail here — that gap is the whole thesis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import registry
from .analysis import (
    correct_prevalence, correct_ci, correct_mean, correct_quantile,
    weighted_mean, weighted_quantile,
    design_based_mean_ci, design_based_quantile_ci,
    PrevalenceResult, DesignCI,
)
from .concepts import Concept

PASS = "PASS"
FAIL = "FAIL"
DESCRIPTIVE = "DESCRIPTIVE"  # documented, no executable statistic


@dataclass
class LintResult:
    ok: bool
    messages: list[str] = field(default_factory=list)


@dataclass
class VerifyResult:
    concept_id: str
    verdict: str
    lint: LintResult
    statistic: str = ""
    claimed_pct: float | None = None
    correct_pct: float | None = None
    delta_pp: float | None = None
    tolerance_pct: float | None = None
    diagnosis: list[str] = field(default_factory=list)
    correct_detail: str = ""
    seeded_defect: bool = False
    # Design-based 95% CI for prevalence concepts (Taylor linearization). None for
    # mean/quantile concepts, whose interval is carried in `correct_detail` instead.
    ci: DesignCI | None = None
    # The kind of statistic ("prevalence"|"mean"|"quantile") and its unit ("%"|"years"…).
    kind: str = "prevalence"
    unit: str = "%"

    @property
    def caught(self) -> bool:
        """True when execution caught a wrong number that the lint did not."""
        return self.verdict == FAIL and self.lint.ok


def lint_concept(concept: Concept, known_ids: set[str]) -> LintResult:
    """Cheap structural checks: prose present, links resolve. No statistics."""
    msgs: list[str] = []
    if not concept.prose.strip():
        msgs.append("empty prose")
    for link in concept.links:
        if link not in known_ids and link not in registry.REGISTRY:
            msgs.append(f"dead link: {link}")
    if concept.variable not in registry.REGISTRY:
        msgs.append(f"unknown variable: {concept.variable}")
    return LintResult(ok=not msgs, messages=msgs)


def _diagnose(concept: Concept, correct: PrevalenceResult) -> list[str]:
    """Explain *why* a claim diverges from the correct computation."""
    out: list[str] = []
    m = concept.method
    if m is None:
        return out
    if not m.weighted:
        out.append(
            "method is UNWEIGHTED; NHIS estimates require survey weights "
            f"({registry.get(concept.variable).weight})"
        )
    correct_universe = (
        concept.analytical_universe
        if concept.analytical_universe is not None
        else registry.get(concept.variable).universe_expr
    )
    if (m.universe_expr or None) != (correct_universe or None):
        out.append(
            f"universe is {m.universe_expr or 'whole sample'!r}; "
            f"correct analytical universe is {correct_universe or 'all adults'!r}"
        )
    return out


def _correct_universe(concept: Concept) -> str | None:
    return (
        concept.analytical_universe
        if concept.analytical_universe is not None
        else registry.get(concept.variable).universe_expr
    )


def _diagnose_continuous(df: pd.DataFrame, concept: Concept, correct_value: float) -> list[str]:
    """Explain *why* a mean/quantile claim diverges — executed, not guessed.

    Recomputes the flawed variants (unweighted; non-substantive codes retained) and, when
    one reproduces the claimed value, names that as the cause. Weighting and the universe
    are checked the same way prevalence claims are.
    """
    out: list[str] = []
    var = registry.get(concept.variable)
    universe = _correct_universe(concept)
    m = concept.method
    tol = concept.tolerance_pct

    if m is not None and not m.weighted:
        out.append(
            "method is UNWEIGHTED; NHIS estimates require survey weights "
            f"({var.weight})"
        )
    if m is not None and (m.universe_expr or None) != (universe or None):
        out.append(
            f"universe is {m.universe_expr or 'whole sample'!r}; "
            f"correct analytical universe is {universe or 'all adults'!r}"
        )

    claimed = concept.value_pct
    # Did the author forget to drop the non-substantive codes? Probe the "retained all codes"
    # variant using the codes actually present in the data (not a fixed 0-99 range), so it
    # covers whatever non-substantive band this variable uses — 96-99 for age/height, but
    # 996-999 for weight — and can name the specific retained codes.
    observed = tuple(sorted(int(v) for v in df[concept.variable].dropna().unique()))
    retained = tuple(c for c in observed if c not in var.valid_codes)
    if concept.kind == "mean":
        unweighted = weighted_mean(
            df, concept.variable, universe_expr=universe,
            valid_codes=var.valid_codes, weighted=False, weight_var=var.weight,
        ).value
        not_dropped = weighted_mean(
            df, concept.variable, universe_expr=universe,
            valid_codes=observed, weighted=True, weight_var=var.weight,
        ).value
    else:
        q = concept.quantile_q if concept.quantile_q is not None else 0.5
        unweighted = weighted_quantile(
            df, concept.variable, q, universe_expr=universe,
            valid_codes=var.valid_codes, weighted=False, weight_var=var.weight,
        ).value
        not_dropped = weighted_quantile(
            df, concept.variable, q, universe_expr=universe,
            valid_codes=observed, weighted=True, weight_var=var.weight,
        ).value

    # Attribute to the single flawed variant that best reproduces the claim. Both variants
    # can land within tolerance by coincidence (e.g. unweighting and retaining 96-99 shift a
    # mean similarly), so reporting both mis-attributes a second cause — pick the closest.
    variant_msgs = {
        "unweighted": (
            f"claim ({claimed}) matches the UNWEIGHTED estimate ({unweighted:.2f}), "
            f"not the survey-weighted one ({correct_value:.2f})"
        ),
        "not_dropped": (
            f"claim ({claimed}) retains non-substantive codes "
            f"({', '.join(map(str, retained)) or 'outside valid_codes'}); dropping them via "
            f"the registry valid_codes gives {correct_value:.2f}"
        ),
    }
    variants = [
        (abs(claimed - unweighted), "unweighted", unweighted),
        (abs(claimed - not_dropped), "not_dropped", not_dropped),
    ]
    matches = [v for v in variants if v[0] <= tol and abs(v[2] - correct_value) > tol]
    if matches:
        out.append(variant_msgs[min(matches)[1]])
    if not out:
        out.append(
            f"claim ({claimed}) does not match the registry-correct value "
            f"({correct_value:.2f})"
        )
    return out


def _verify_continuous(
    df: pd.DataFrame, concept: Concept, lint: LintResult
) -> VerifyResult:
    if concept.kind == "mean":
        result = correct_mean(df, concept.variable, analytical_universe=concept.analytical_universe)
        detail = analysis_mean_detail(df, concept)
    else:
        q = concept.quantile_q if concept.quantile_q is not None else 0.5
        result = correct_quantile(
            df, concept.variable, q, analytical_universe=concept.analytical_universe
        )
        detail = analysis_quantile_detail(df, concept, q)
    correct_value = result.value
    delta = abs(concept.value_pct - correct_value)
    diagnosis = [] if delta <= concept.tolerance_pct else _diagnose_continuous(
        df, concept, correct_value
    )
    return VerifyResult(
        concept_id=concept.id,
        verdict=PASS if not diagnosis else FAIL,
        lint=lint,
        statistic=concept.statistic,
        claimed_pct=concept.value_pct,
        correct_pct=round(correct_value, 2),
        delta_pp=round(delta, 2),
        tolerance_pct=concept.tolerance_pct,
        diagnosis=diagnosis,
        correct_detail=detail,
        seeded_defect=concept.seeded_defect,
        kind=concept.kind,
        unit=concept.unit,
    )


def analysis_mean_detail(df: pd.DataFrame, concept: Concept) -> str:
    ci = design_based_mean_ci(
        df, concept.variable, universe_expr=_correct_universe(concept),
        valid_codes=registry.get(concept.variable).valid_codes,
        weight_var=registry.get(concept.variable).weight,
    )
    return ci.summary()


def analysis_quantile_detail(df: pd.DataFrame, concept: Concept, q: float) -> str:
    ci = design_based_quantile_ci(
        df, concept.variable, q, universe_expr=_correct_universe(concept),
        valid_codes=registry.get(concept.variable).valid_codes,
        weight_var=registry.get(concept.variable).weight,
    )
    return ci.summary()


def verify_concept(
    df: pd.DataFrame, concept: Concept, known_ids: set[str]
) -> VerifyResult:
    lint = lint_concept(concept, known_ids)

    # Descriptive concept: nothing to execute. Structural documentation only.
    if not concept.is_analytical:
        return VerifyResult(
            concept_id=concept.id,
            verdict=DESCRIPTIVE if lint.ok else FAIL,
            lint=lint,
            seeded_defect=concept.seeded_defect,
        )

    # Continuous / distributional claims (mean, quantile) dispatch to their own path.
    if concept.kind in ("mean", "quantile"):
        return _verify_continuous(df, concept, lint)

    correct = correct_prevalence(
        df, concept.variable, analytical_universe=concept.analytical_universe
    )
    ci = correct_ci(df, concept.variable, analytical_universe=concept.analytical_universe)
    delta = abs(concept.value_pct - correct.value_pct)
    diagnosis = [] if delta <= concept.tolerance_pct else _diagnose(concept, correct)

    # CI-precision check: a claimed CI that is materially tighter than the design-based CI
    # understates uncertainty (typically by ignoring the design effect). Caught like any
    # other confidently-wrong number.
    if concept.claimed_ci is not None:
        claimed_hw = (concept.claimed_ci[1] - concept.claimed_ci[0]) / 2
        design_hw = (ci.uci_pct - ci.lci_pct) / 2
        if claimed_hw < design_hw - 0.1:  # 0.1pp slack
            diagnosis.append(
                f"claimed 95% CI half-width {claimed_hw:.2f}pp understates the design-based "
                f"{design_hw:.2f}pp — it ignores the survey design effect (DEFF {ci.deff:.2f})"
            )

    return VerifyResult(
        concept_id=concept.id,
        verdict=PASS if not diagnosis else FAIL,
        lint=lint,
        statistic=concept.statistic,
        claimed_pct=concept.value_pct,
        correct_pct=round(correct.value_pct, 2),
        delta_pp=round(delta, 2),
        tolerance_pct=concept.tolerance_pct,
        diagnosis=diagnosis,
        correct_detail=ci.summary(),
        seeded_defect=concept.seeded_defect,
        ci=ci,
    )


def verify_all(df: pd.DataFrame, concept_list: list[Concept]) -> list[VerifyResult]:
    known = {c.id for c in concept_list} | {c.variable for c in concept_list}
    return [verify_concept(df, c, known) for c in concept_list]
