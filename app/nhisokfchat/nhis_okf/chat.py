"""The grounded agent's brain: its system prompt and its two tool-logic functions.

A reader should be able to open this file and see what the agent knows and does:

  1. OKF_ANALYST_PROMPT  — the system prompt (the rules the model must follow)
  2. search_okf          — retrieve a precomputed verified concept from the OKF bundle
  3. analyze_rows        — compute a survey-weighted AGGREGATE for an ad-hoc subgroup
                           (over the row-level microdata, but it NEVER returns rows)

These are plain functions. `main.py` wraps them in the two `@tool`-decorated Strands
tools it hands to the agent (`tool_search_okf`, `tool_analyze_rows` — the names this
prompt refers to). All the supporting machinery — answer formatting, the microdata
loader, the universe injection-gate, model/agent construction — lives in `helpers.py`.
"""

from __future__ import annotations

from . import helpers
from .retrieval import verified_variables

OKF_ANALYST_PROMPT = """\
You answer questions about U.S. health survey statistics using ONLY the two verified,
deterministic tools below. Never use outside knowledge for a figure.

Your tools:
- tool_search_okf(query): retrieval over the verified OKF bundle. Use it for a precomputed
  concept the bundle already carries (e.g. insulin use among diagnosed adults). Quote the
  exact survey-weighted percentage and cite the concept id in brackets, e.g. [DIBINS_A].
- tool_analyze_rows(variable, universe, stat, q): a deterministic, survey-weighted
  computation with a design-based confidence interval. Use it for an ad-hoc weighted
  SUBGROUP a concept does not already carry (e.g. a figure restricted to women, or a mean
  age at diagnosis for a subset). `variable` must be a verified variable; `universe` is a
  pandas row filter over the microdata, e.g. "DIBEV_A == 1 & SEX_A == 2". `stat` is one of
  prevalence | mean | quantile. It returns only an aggregate estimate and its CI — never
  individual rows.

Hard rules:
- For any FIGURE (a percentage, count, mean, rate, "how many/what share"): use ONLY
  tool_search_okf (a precomputed concept) or tool_analyze_rows (one ad-hoc weighted
  subgroup). NEVER invent, estimate, or guess a number.
- If a tool returns nothing relevant, NO_VERIFIED_CONCEPTS_FOUND, or a message beginning
  with REFUSED, say you cannot answer that from the verified bundle. Do NOT substitute a
  number of your own.
- ALWAYS state the survey-weighted basis (the universe/denominator and that it is
  weighted) with any figure, and report the confidence interval when the tool gives one.
- These are public, aggregate survey estimates. This is not medical advice; make no
  individual-level inference and give no clinical recommendation. You only ever see
  verified aggregates — you cannot access or return individual survey records.
- Be concise and factual.
"""


def search_okf(query: str) -> str:
    """Search the verified NHIS OKF bundle and return matching concepts with their
    survey-weighted figures. Returns NO_VERIFIED_CONCEPTS_FOUND if nothing matches."""
    return helpers.format_hits(helpers.retrieve(query))


def analyze_rows(
    variable: str, universe: str, stat: str = "prevalence", q: float = 0.5
) -> str:
    """Compute a survey-weighted AGGREGATE + design-based CI for an ad-hoc subpopulation of a
    VERIFIED NHIS variable. Computes over the row-level microdata but returns only an
    aggregate estimate and its confidence interval — NEVER individual rows.

    Three gates run in order before any computation, and none may be reordered or weakened:
      1. verified-variable check — refuse a variable with no verified concept in the bundle;
      2. continuous-prevalence guard — refuse a prevalence for a continuous measure (it would
         emit a confident, meaningless 0.00%); steer to mean/quantile instead;
      3. universe allow-list — `helpers.validate_agent_universe` must pass BEFORE `analysis`
         is imported or used, because the agent-composed `universe` reaches `df.eval`
         (the `injection-sink@universe-eval` seam).
    """
    allowed = verified_variables()
    if variable not in allowed:
        return (
            f"REFUSED: {variable!r} is not backed by a verified concept in the compiled "
            f"bundle, so no grounded figure can be computed. Verified variables: "
            f"{', '.join(sorted(allowed)) or '(none compiled)'}."
        )
    # Core-invariant guard: prevalence (a percentage) is undefined for a continuous measure
    # with no affirmative ("yes") code — computing it would return a confident 0.00% with a
    # real-looking CI, exactly the structurally-valid-but-statistically-wrong number this
    # project exists to refuse. Steer to a mean/quantile instead of emitting a false 0%.
    if stat == "prevalence":
        from . import registry

        var = registry.REGISTRY.get(variable)
        if var is not None and not var.affirmative_codes:
            return (
                f"REFUSED: {variable!r} is a continuous measure with no affirmative code, so a "
                f"prevalence (percentage) is undefined for it. Ask for stat='mean' or "
                f"stat='quantile' instead (e.g. the mean age at diagnosis)."
            )
    # Injection gate: the agent-composed universe must pass the allow-list before it can
    # reach analysis._mask -> df.eval (the injection-sink seam).
    try:
        helpers.validate_agent_universe(universe)
    except ValueError as exc:
        return f"REFUSED: universe not allowed — {exc}."

    from . import analysis

    try:
        res = analysis.subpopulation_stat(
            helpers.microdata(), variable, universe_expr=universe, stat=stat, q=q
        )
    except Exception as exc:
        return f"REFUSED: could not compute a grounded figure — {exc}."
    return res.summary()
