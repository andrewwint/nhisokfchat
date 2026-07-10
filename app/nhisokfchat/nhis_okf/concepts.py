"""Concepts: the documented analytical claims that get compiled into the OKF bundle.

A concept is what a human analyst (or a passive RAG over the codebook PDFs) would
*write down*: a variable, prose, links, and a headline statistic with a stated method
and a claimed value. The markdown can be perfectly clean and every link can resolve
while the claimed number is still wrong. Catching that is the whole project, and it is
`verify.py`'s job — not this module's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONCEPTS_DIR = REPO_ROOT / "concepts"


@dataclass
class ClaimMethod:
    """The method a concept *says* it used to produce its number."""

    universe_expr: str | None
    weighted: bool


@dataclass
class Concept:
    id: str
    variable: str
    label: str
    # The denominator the claim's statistic actually targets (registry-correct).
    analytical_universe: str | None
    # Analytical concepts carry a headline statistic; descriptive ones do not.
    statistic: str = ""
    method: ClaimMethod | None = None
    value_pct: float | None = None
    tolerance_pct: float = 0.5
    # The kind of statistic the claim makes: "prevalence" (a % — default, backward
    # compatible), "mean", or "quantile" (both in the variable's own units, not a %).
    kind: str = "prevalence"
    # For quantile claims, the target probability in [0, 1] (e.g. 0.5 for the median).
    quantile_q: float | None = None
    # The unit the claimed value is expressed in ("%" for prevalence; e.g. "years").
    unit: str = "%"
    # Optional claimed 95% CI [low, high] in percentage points, for CI-precision checks.
    claimed_ci: tuple[float, float] | None = None
    links: list[str] = field(default_factory=list)
    prose: str = ""
    # A concept may be deliberately seeded as a defect, to demonstrate the catch.
    seeded_defect: bool = False
    source_path: Path | None = None

    @property
    def is_analytical(self) -> bool:
        return self.value_pct is not None


def _parse(doc: dict, source: Path | None = None) -> Concept:
    claim = doc.get("claim")
    method = None
    statistic = ""
    value_pct = None
    tolerance_pct = 0.5
    kind = "prevalence"
    quantile_q = None
    unit = "%"
    if claim is not None:
        m = claim.get("method", {})
        method = ClaimMethod(
            universe_expr=m.get("universe_expr"),
            weighted=bool(m.get("weighted", True)),
        )
        statistic = claim.get("statistic", "")
        kind = claim.get("kind", "prevalence")
        quantile_q = claim.get("quantile_q")
        quantile_q = float(quantile_q) if quantile_q is not None else None
        # `value` is the units-aware key for mean/quantile; `value_pct` the legacy % key.
        raw_value = claim.get("value", claim.get("value_pct"))
        value_pct = float(raw_value)
        unit = claim.get("unit", "%" if kind == "prevalence" else "")
        # Tolerance is in the claim's units; `tolerance_pct` kept for backward compat.
        tolerance_pct = float(claim.get("tolerance", claim.get("tolerance_pct", 0.5)))
    claimed_ci = None
    if claim is not None and claim.get("ci_95"):
        lo, hi = claim["ci_95"]
        claimed_ci = (float(lo), float(hi))
    return Concept(
        id=doc["id"],
        variable=doc["variable"],
        label=doc.get("label", ""),
        analytical_universe=doc.get("analytical_universe"),
        statistic=statistic,
        method=method,
        value_pct=value_pct,
        tolerance_pct=tolerance_pct,
        kind=kind,
        quantile_q=quantile_q,
        unit=unit,
        claimed_ci=claimed_ci,
        links=list(doc.get("links", [])),
        prose=doc.get("prose", "").strip(),
        seeded_defect=bool(doc.get("seeded_defect", False)),
        source_path=source,
    )


def load_concept(path: str | Path) -> Concept:
    path = Path(path)
    with open(path) as f:
        return _parse(yaml.safe_load(f), source=path)


def load_all(concepts_dir: str | Path = CONCEPTS_DIR) -> list[Concept]:
    concepts_dir = Path(concepts_dir)
    out = [load_concept(p) for p in sorted(concepts_dir.glob("*.yaml"))]
    if not out:
        raise FileNotFoundError(f"no concept YAML files in {concepts_dir}")
    return out
