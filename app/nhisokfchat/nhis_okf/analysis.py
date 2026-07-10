"""Survey-weighted analysis engine for NHIS.

This is the statistical core the data-science skill owns. One generic prevalence
function runs *both* a concept's documented method and the registry-correct method, so
the verifier can compare them on equal footing. Survey weighting is applied by default
because unweighted NHIS counts do not estimate the population.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from . import registry

# Resolve data relative to the repo root so the CLI works from anywhere.
REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DEFAULT_CSV = DATA_DIR / "adult23.csv"
NHIS_2023_ADULT_CSV_ZIP = (
    "https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Datasets/NHIS/2023/adult23csv.zip"
)


@dataclass
class PrevalenceResult:
    """The outcome of one prevalence computation."""

    variable: str
    universe_expr: str | None
    weighted: bool
    value_pct: float
    numerator_unweighted: int
    denominator_unweighted: int
    denominator_weighted: float
    weight_var: str | None

    def summary(self) -> str:
        basis = f"weighted by {self.weight_var}" if self.weighted else "UNWEIGHTED"
        uni = self.universe_expr or "all sample adults"
        return (
            f"{self.value_pct:.2f}% ({basis}; universe: {uni}; "
            f"n={self.denominator_unweighted} unweighted)"
        )


def parquet_twin(csv_path: str | Path) -> Path:
    """The derived `.parquet` cache path that sits next to a data CSV."""
    return Path(csv_path).with_suffix(".parquet")


def table_columns(csv_path: str | Path) -> set[str]:
    """Column names available in the twin (preferred) or the CSV, cheaply."""
    csv_path = Path(csv_path)
    twin = parquet_twin(csv_path)
    if twin.exists():
        import pyarrow.parquet as pq

        return set(pq.ParquetFile(twin).schema_arrow.names)
    return set(pd.read_csv(csv_path, nrows=1).columns)


def load_table(csv_path: str | Path, columns=None) -> pd.DataFrame:
    """Load a data table, preferring the parquet twin and falling back to the CSV.

    Column projection is pushed down to whichever file is read. Requested columns are
    intersected with the columns actually present, so a name absent from a given year's
    file is silently skipped — matching the CSV `usecols` lambda's behavior and avoiding
    the error `pd.read_parquet(columns=...)` raises on a missing column.
    """
    csv_path = Path(csv_path)
    twin = parquet_twin(csv_path)
    if twin.exists():
        proj = None
        if columns is not None:
            available = table_columns(csv_path)
            proj = [c for c in columns if c in available]
        return pd.read_parquet(twin, columns=proj)
    usecols = (lambda c: c in set(columns)) if columns else None
    return pd.read_csv(csv_path, usecols=usecols, low_memory=False)


def materialize_parquet(csv_path: str | Path, *, force: bool = False) -> Path:
    """Write a `.parquet` twin next to a data CSV (idempotent).

    CSV stays the fetched source of truth; parquet is a derived cache. The twin is
    rebuilt only when missing, stale (older than the CSV), or `force`d.
    """
    csv_path = Path(csv_path)
    twin = parquet_twin(csv_path)
    if (
        not force
        and twin.exists()
        and twin.stat().st_mtime >= csv_path.stat().st_mtime
    ):
        return twin
    pd.read_csv(csv_path, low_memory=False).to_parquet(twin, index=False)
    return twin


def load_microdata(csv_path: str | Path = DEFAULT_CSV, columns=None) -> pd.DataFrame:
    """Load the NHIS Sample Adult data, optionally restricting to `columns`.

    Prefers the parquet twin when present and falls back to the CSV; both paths yield
    identical estimates.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists() and not parquet_twin(csv_path).exists():
        raise FileNotFoundError(
            f"{csv_path} not found. Run `nhis fetch` to download the public-use file."
        )
    return load_table(csv_path, columns)


def _mask(df: pd.DataFrame, expr: str | None) -> pd.Series:
    """Boolean mask for a universe expression, or all-True when expr is None.

    NOTE (trust boundary): `expr` comes from registry/concept files authored in this
    repo and the tool runs locally, so `df.eval` is safe here. If concepts ever accept
    untrusted input, or this gains a web surface, replace `eval` with a parsed,
    allow-listed predicate — `eval` on untrusted strings is a code-injection vector.
    """
    if expr is None:
        return pd.Series(True, index=df.index)
    return df.eval(expr)


def compute_prevalence(
    df: pd.DataFrame,
    variable: str,
    *,
    universe_expr: str | None,
    affirmative_codes: tuple[int, ...],
    valid_codes: tuple[int, ...],
    weighted: bool = True,
    weight_var: str = registry.SAMPLE_ADULT_WEIGHT,
    denominator: str = "valid",
) -> PrevalenceResult:
    """Prevalence of `affirmative_codes` among a denominator within a universe.

    Every knob is explicit so the same function can express both a correct analysis
    and a flawed one (wrong universe, weighting off, wrong denominator). The verifier
    exploits that.

    `denominator`:
      * "valid" (correct) — only substantive responses count toward the denominator.
      * "all_in_universe" (a classic skip-pattern error) — every row in the universe
        counts, so people who were never asked are silently treated as non-affirmative.
        With universe=None this is the "% of the whole sample" mistake.
    """
    in_universe = _mask(df, universe_expr)
    if denominator == "all_in_universe":
        denom_rows = df[in_universe]
    elif denominator == "valid":
        denom_rows = df[in_universe & df[variable].isin(valid_codes)]
    else:
        raise ValueError(f"unknown denominator mode: {denominator!r}")
    num_rows = denom_rows[denom_rows[variable].isin(affirmative_codes)]

    if weighted:
        w = denom_rows[weight_var]
        denom_w = float(w.sum())
        num_w = float(num_rows[weight_var].sum())
        value = (num_w / denom_w * 100.0) if denom_w else 0.0
    else:
        denom_w = float(len(denom_rows))
        value = (len(num_rows) / denom_w * 100.0) if denom_w else 0.0

    return PrevalenceResult(
        variable=variable,
        universe_expr=universe_expr,
        weighted=weighted,
        value_pct=value,
        numerator_unweighted=len(num_rows),
        denominator_unweighted=len(denom_rows),
        denominator_weighted=denom_w,
        weight_var=weight_var if weighted else None,
    )


def correct_prevalence(
    df: pd.DataFrame, variable: str, *, analytical_universe: str | None = None
) -> PrevalenceResult:
    """The registry-correct prevalence: true universe + mandatory weighting.

    `analytical_universe` overrides the registry's *question* universe when the claim
    targets a narrower analytical denominator (e.g. insulin use among diagnosed
    diabetics is DIBEV_A == 1, not the prediabetes-inclusive question universe).
    """
    var = registry.get(variable)
    universe = analytical_universe if analytical_universe is not None else var.universe_expr
    return compute_prevalence(
        df,
        variable,
        universe_expr=universe,
        affirmative_codes=var.affirmative_codes,
        valid_codes=var.valid_codes,
        weighted=True,
        weight_var=var.weight,
    )


# --- Continuous / distributional statistics --------------------------------------------
#
# Age-at-diagnosis and the like are not yes/no rates, so prevalence does not apply. The
# survey-weighted mean and quantile follow the same explicit-knobs pattern as
# `compute_prevalence`: weighting can be turned off and the substantive-code filter is
# passed in, so a flawed method (unweighted, or non-substantive codes not dropped) stays
# expressible and therefore catchable by the verifier.


@dataclass
class MeanResult:
    """The outcome of one survey-weighted mean computation (units of the variable)."""

    variable: str
    universe_expr: str | None
    weighted: bool
    value: float
    unweighted_n: int
    denominator_weighted: float
    weight_var: str | None

    def summary(self) -> str:
        basis = f"weighted by {self.weight_var}" if self.weighted else "UNWEIGHTED"
        uni = self.universe_expr or "all sample adults"
        return (
            f"{self.value:.2f} ({basis}; universe: {uni}; "
            f"n={self.unweighted_n} unweighted)"
        )


@dataclass
class QuantileResult:
    """The outcome of one survey-weighted quantile computation (units of the variable)."""

    variable: str
    universe_expr: str | None
    q: float
    weighted: bool
    value: float
    unweighted_n: int
    denominator_weighted: float
    weight_var: str | None

    def summary(self) -> str:
        basis = f"weighted by {self.weight_var}" if self.weighted else "UNWEIGHTED"
        uni = self.universe_expr or "all sample adults"
        return (
            f"q{self.q:g}={self.value:.2f} ({basis}; universe: {uni}; "
            f"n={self.unweighted_n} unweighted)"
        )


def _substantive(
    df: pd.DataFrame, variable: str, universe_expr: str | None, valid_codes: tuple[int, ...]
) -> pd.DataFrame:
    """Rows in the universe whose response is a substantive (valid) value."""
    return df[_mask(df, universe_expr) & df[variable].isin(valid_codes)]


def weighted_mean(
    df: pd.DataFrame,
    variable: str,
    *,
    universe_expr: str | None,
    valid_codes: tuple[int, ...],
    weighted: bool = True,
    weight_var: str = registry.SAMPLE_ADULT_WEIGHT,
) -> MeanResult:
    """Survey-weighted mean of `variable` over the substantive rows of a universe.

    Non-substantive codes (e.g. DIBAGETC_A's 96-99) are excluded by `valid_codes`;
    turning `weighted` off, or widening `valid_codes` to include 96-99, expresses the
    two classic mistakes the verifier catches.
    """
    d = _substantive(df, variable, universe_expr, valid_codes)
    y = d[variable].to_numpy(dtype=float)
    if weighted:
        w = d[weight_var].to_numpy(dtype=float)
        denom_w = float(w.sum())
        value = float((w * y).sum() / denom_w) if denom_w else 0.0
    else:
        denom_w = float(len(d))
        value = float(y.mean()) if len(d) else 0.0
    return MeanResult(
        variable=variable,
        universe_expr=universe_expr,
        weighted=weighted,
        value=value,
        unweighted_n=len(d),
        denominator_weighted=denom_w,
        weight_var=weight_var if weighted else None,
    )


def weighted_quantile(
    df: pd.DataFrame,
    variable: str,
    q: float,
    *,
    universe_expr: str | None,
    valid_codes: tuple[int, ...],
    weighted: bool = True,
    weight_var: str = registry.SAMPLE_ADULT_WEIGHT,
) -> QuantileResult:
    """Survey-weighted `q`-quantile (q in [0, 1]) over the substantive rows of a universe."""
    import numpy as np

    d = _substantive(df, variable, universe_expr, valid_codes)
    y = d[variable].to_numpy(dtype=float)
    w = (
        d[weight_var].to_numpy(dtype=float)
        if weighted
        else np.ones(len(d), dtype=float)
    )
    if len(d) == 0:
        value = 0.0
        denom_w = 0.0
    else:
        order = np.argsort(y)
        y, w = y[order], w[order]
        # Cumulative weight at the midpoint of each observation's mass, normalized to [0, 1].
        cum = (np.cumsum(w) - 0.5 * w) / w.sum()
        value = float(np.interp(q, cum, y))
        denom_w = float(w.sum())
    return QuantileResult(
        variable=variable,
        universe_expr=universe_expr,
        q=q,
        weighted=weighted,
        value=value,
        unweighted_n=len(d),
        denominator_weighted=denom_w,
        weight_var=weight_var if weighted else None,
    )


def correct_mean(
    df: pd.DataFrame, variable: str, *, analytical_universe: str | None = None
) -> MeanResult:
    """Registry-correct weighted mean: true universe + mandatory weighting + valid codes."""
    var = registry.get(variable)
    universe = analytical_universe if analytical_universe is not None else var.universe_expr
    return weighted_mean(
        df, variable, universe_expr=universe,
        valid_codes=var.valid_codes, weighted=True, weight_var=var.weight,
    )


def correct_quantile(
    df: pd.DataFrame, variable: str, q: float, *, analytical_universe: str | None = None
) -> QuantileResult:
    """Registry-correct weighted quantile: true universe + mandatory weighting + valid codes."""
    var = registry.get(variable)
    universe = analytical_universe if analytical_universe is not None else var.universe_expr
    return weighted_quantile(
        df, variable, q, universe_expr=universe,
        valid_codes=var.valid_codes, weighted=True, weight_var=var.weight,
    )


@dataclass
class DesignCI:
    """A design-based (complex-survey) confidence interval for a proportion."""

    estimate_pct: float
    se_pp: float
    lci_pct: float
    uci_pct: float
    deff: float  # design effect: design variance / simple-random-sampling variance
    n_psu: int
    n_strata: int

    def summary(self) -> str:
        return (
            f"{self.estimate_pct:.2f}% (95% CI {self.lci_pct:.2f}-{self.uci_pct:.2f}; "
            f"design-based SE {self.se_pp:.2f}pp, DEFF {self.deff:.2f})"
        )


def design_based_ci(
    df: pd.DataFrame,
    variable: str,
    *,
    universe_expr: str | None,
    affirmative_codes: tuple[int, ...],
    valid_codes: tuple[int, ...],
    weight_var: str = registry.SAMPLE_ADULT_WEIGHT,
    strata_var: str = registry.DESIGN_STRATUM,
    psu_var: str = registry.DESIGN_PSU,
    z: float = 1.96,
) -> DesignCI:
    """Taylor-series linearization variance for a weighted proportion under a stratified,
    multistage (with-replacement) design — the standard public-use-file method.

    The proportion is the ratio estimator R = Sum(w*y) / Sum(w). The linearized residual
    z_i = w_i (y_i - R) is summed to PSU totals within strata, and the variance is the
    stratified sum of between-PSU variance, divided by Sum(w)^2. Validated against the
    required property that the design effect exceeds 1 for clustered data.
    """
    import numpy as np

    d = df[_mask(df, universe_expr) & df[variable].isin(valid_codes)]
    y = d[variable].isin(affirmative_codes).to_numpy(dtype=float)
    w = d[weight_var].to_numpy(dtype=float)
    total_w = w.sum()
    R = float((w * y).sum() / total_w)
    z_lin = w * (y - R)

    psu = pd.DataFrame({"h": d[strata_var].to_numpy(), "a": d[psu_var].to_numpy(),
                        "z": z_lin}).groupby(["h", "a"], sort=False)["z"].sum().reset_index()
    var_total, n_psu = 0.0, len(psu)
    strata = psu.groupby("h")
    for _, grp in strata:
        nh = len(grp)
        if nh < 2:  # singleton stratum contributes no within-stratum variance
            continue
        zbar = grp["z"].mean()
        var_total += nh / (nh - 1) * float(((grp["z"] - zbar) ** 2).sum())
    var_R = var_total / total_w ** 2
    se = float(np.sqrt(var_R))

    # Design effect vs simple random sampling (correctness sanity: DEFF > 1 for clusters).
    n = len(d)
    srs_var = R * (1 - R) / n if n else 0.0
    deff = (var_R / srs_var) if srs_var > 0 else float("nan")

    return DesignCI(
        estimate_pct=R * 100,
        se_pp=se * 100,
        lci_pct=(R - z * se) * 100,
        uci_pct=(R + z * se) * 100,
        deff=deff,
        n_psu=n_psu,
        n_strata=int(strata.ngroups),
    )


def correct_ci(
    df: pd.DataFrame, variable: str, *, analytical_universe: str | None = None
) -> DesignCI:
    """Registry-correct design-based CI: true universe + mandatory weighting + design vars."""
    var = registry.get(variable)
    universe = analytical_universe if analytical_universe is not None else var.universe_expr
    return design_based_ci(
        df, variable, universe_expr=universe,
        affirmative_codes=var.affirmative_codes, valid_codes=var.valid_codes,
        weight_var=var.weight,
    )


def _stratified_psu_variance(
    strata: pd.Series, psu: pd.Series, z_lin, total_w: float
) -> float:
    """Stratified between-PSU variance of a linearized total, divided by Sum(w)^2.

    The shared core of the Taylor-linearization variance for any ratio estimator
    R = Sum(w*y)/Sum(w): the residual z_i = w_i (y_i - R) is summed to PSU totals within
    strata, and singleton strata contribute no within-stratum variance.
    """
    psu_df = pd.DataFrame({"h": strata.to_numpy(), "a": psu.to_numpy(), "z": z_lin})
    psu_tot = psu_df.groupby(["h", "a"], sort=False)["z"].sum().reset_index()
    var_total = 0.0
    for _, grp in psu_tot.groupby("h"):
        nh = len(grp)
        if nh < 2:
            continue
        zbar = grp["z"].mean()
        var_total += nh / (nh - 1) * float(((grp["z"] - zbar) ** 2).sum())
    return var_total / total_w ** 2


@dataclass
class MeanCI:
    """A design-based (complex-survey) confidence interval for a weighted mean."""

    estimate: float
    se: float
    lci: float
    uci: float
    n_psu: int
    n_strata: int

    def summary(self) -> str:
        return (
            f"{self.estimate:.2f} (95% CI {self.lci:.2f}-{self.uci:.2f}; "
            f"design-based SE {self.se:.2f})"
        )


def design_based_mean_ci(
    df: pd.DataFrame,
    variable: str,
    *,
    universe_expr: str | None,
    valid_codes: tuple[int, ...],
    weight_var: str = registry.SAMPLE_ADULT_WEIGHT,
    strata_var: str = registry.DESIGN_STRATUM,
    psu_var: str = registry.DESIGN_PSU,
    z: float = 1.96,
) -> MeanCI:
    """Taylor-linearization CI for a survey-weighted mean (the ratio Sum(w*y)/Sum(w))."""
    import numpy as np

    d = _substantive(df, variable, universe_expr, valid_codes)
    y = d[variable].to_numpy(dtype=float)
    w = d[weight_var].to_numpy(dtype=float)
    total_w = w.sum()
    R = float((w * y).sum() / total_w)
    var_R = _stratified_psu_variance(d[strata_var], d[psu_var], w * (y - R), total_w)
    se = float(np.sqrt(var_R))
    psu = pd.DataFrame({"h": d[strata_var].to_numpy(), "a": d[psu_var].to_numpy()})
    return MeanCI(
        estimate=R, se=se, lci=R - z * se, uci=R + z * se,
        n_psu=len(psu.drop_duplicates()), n_strata=int(d[strata_var].nunique()),
    )


def design_based_quantile_ci(
    df: pd.DataFrame,
    variable: str,
    q: float,
    *,
    universe_expr: str | None,
    valid_codes: tuple[int, ...],
    weight_var: str = registry.SAMPLE_ADULT_WEIGHT,
    strata_var: str = registry.DESIGN_STRATUM,
    psu_var: str = registry.DESIGN_PSU,
    z: float = 1.96,
) -> MeanCI:
    """Woodruff design-based CI for a weighted quantile.

    Build the design-based SE of the estimated CDF value at the point estimate, form the
    proportion interval [q - z*se, q + z*se], and map its bounds back through the weighted
    empirical CDF to the variable's units. Reported in a `MeanCI` (units of the variable).
    """
    import numpy as np

    point = weighted_quantile(
        df, variable, q, universe_expr=universe_expr, valid_codes=valid_codes,
        weighted=True, weight_var=weight_var,
    ).value
    d = _substantive(df, variable, universe_expr, valid_codes)
    y = d[variable].to_numpy(dtype=float)
    w = d[weight_var].to_numpy(dtype=float)
    total_w = w.sum()
    ind = (y <= point).astype(float)  # indicator whose weighted mean is F(point) ~= q
    P = float((w * ind).sum() / total_w)
    var_P = _stratified_psu_variance(d[strata_var], d[psu_var], w * (ind - P), total_w)
    se_p = float(np.sqrt(var_P))
    order = np.argsort(y)
    ys, ws = y[order], w[order]
    cum = (np.cumsum(ws) - 0.5 * ws) / ws.sum()
    lci = float(np.interp(max(0.0, q - z * se_p), cum, ys))
    uci = float(np.interp(min(1.0, q + z * se_p), cum, ys))
    psu = pd.DataFrame({"h": d[strata_var].to_numpy(), "a": d[psu_var].to_numpy()})
    return MeanCI(
        estimate=point, se=se_p, lci=lci, uci=uci,
        n_psu=len(psu.drop_duplicates()), n_strata=int(d[strata_var].nunique()),
    )


@dataclass
class SubpopulationResult:
    """A survey-weighted aggregate for an arbitrary subpopulation, with its design CI.

    This is the *only* thing the subpopulation query returns — a scalar estimate and its
    interval, never a set of individual rows. That is the aggregate-only safety invariant.
    """

    variable: str
    universe_expr: str | None
    stat: str  # "prevalence" | "mean" | "quantile"
    unit: str  # "%" for prevalence, "" for units-of-variable mean/quantile
    estimate: float
    lci: float
    uci: float
    se: float
    unweighted_n: int
    denominator_weighted: float
    weight_var: str
    q: float | None = None

    def summary(self) -> str:
        uni = self.universe_expr or "all sample adults"
        label = self.stat if self.q is None else f"{self.stat} (q={self.q:g})"
        return (
            f"{self.variable} {label}: {self.estimate:.2f}{self.unit} "
            f"(95% CI {self.lci:.2f}-{self.uci:.2f}{self.unit}; design-based SE "
            f"{self.se:.2f}; weighted by {self.weight_var}; universe: {uni}; "
            f"n={self.unweighted_n} unweighted, denominator "
            f"{self.denominator_weighted:,.0f} weighted)"
        )


def subpopulation_stat(
    df: pd.DataFrame,
    variable: str,
    *,
    universe_expr: str | None,
    stat: str = "prevalence",
    q: float = 0.5,
) -> SubpopulationResult:
    """Survey-weighted aggregate + design-based CI for a subpopulation.

    `universe_expr` is an arbitrary pandas row filter (the *means* of subsetting); the
    return is always a single aggregate object (the *output*). There is deliberately no
    code path that returns the underlying rows — the safety scope forbids exposing
    individual records. Weighting is mandatory and uses the registry's weight/design vars.
    """
    var = registry.get(variable)
    # Empty subpopulation: refuse rather than report a fabricated 0.0 with a NaN interval.
    # An arbitrary universe that matches no substantive rows has no estimate to report, and
    # emitting "0.0" would be exactly the confidently-wrong number this project exists to
    # prevent — on the one surface (ad-hoc query) that bypasses the concept-verification gate.
    if _substantive(df, variable, universe_expr, var.valid_codes).empty:
        raise ValueError(
            f"empty subpopulation: universe {universe_expr!r} matches no substantive "
            f"{variable} rows — no weighted estimate is defined"
        )
    if stat == "prevalence":
        pr = compute_prevalence(
            df, variable, universe_expr=universe_expr,
            affirmative_codes=var.affirmative_codes, valid_codes=var.valid_codes,
            weighted=True, weight_var=var.weight,
        )
        ci = design_based_ci(
            df, variable, universe_expr=universe_expr,
            affirmative_codes=var.affirmative_codes, valid_codes=var.valid_codes,
            weight_var=var.weight,
        )
        return SubpopulationResult(
            variable=variable, universe_expr=universe_expr, stat=stat, unit="%",
            estimate=pr.value_pct, lci=ci.lci_pct, uci=ci.uci_pct, se=ci.se_pp,
            unweighted_n=pr.denominator_unweighted,
            denominator_weighted=pr.denominator_weighted, weight_var=var.weight,
        )
    if stat == "mean":
        mr = weighted_mean(
            df, variable, universe_expr=universe_expr,
            valid_codes=var.valid_codes, weighted=True, weight_var=var.weight,
        )
        ci = design_based_mean_ci(
            df, variable, universe_expr=universe_expr,
            valid_codes=var.valid_codes, weight_var=var.weight,
        )
        return SubpopulationResult(
            variable=variable, universe_expr=universe_expr, stat=stat, unit="",
            estimate=mr.value, lci=ci.lci, uci=ci.uci, se=ci.se,
            unweighted_n=mr.unweighted_n,
            denominator_weighted=mr.denominator_weighted, weight_var=var.weight,
        )
    if stat == "quantile":
        qr = weighted_quantile(
            df, variable, q, universe_expr=universe_expr,
            valid_codes=var.valid_codes, weighted=True, weight_var=var.weight,
        )
        ci = design_based_quantile_ci(
            df, variable, q, universe_expr=universe_expr,
            valid_codes=var.valid_codes, weight_var=var.weight,
        )
        return SubpopulationResult(
            variable=variable, universe_expr=universe_expr, stat=stat, unit="",
            estimate=qr.value, lci=ci.lci, uci=ci.uci, se=ci.se,
            unweighted_n=qr.unweighted_n,
            denominator_weighted=qr.denominator_weighted, weight_var=var.weight, q=q,
        )
    raise ValueError(f"unknown stat kind: {stat!r} (use prevalence|mean|quantile)")


# --- Deterministic weighted groupby table ----------------------------------------------
#
# A "by-group" answer (insulin use by sex, mean weight by BMI category) is just the same
# registry-correct, weighted `subpopulation_stat` computed once per group value, assembled
# into a table here rather than by an LLM looping over the single-cell tool. Every cell is
# an aggregate + design-based CI; there is no row path. The measured `variable` is grounded
# where this is called (CLI / agent tool); the grouping column only partitions.

# Cap on the number of groups: guards a mistaken groupby on a near-continuous column from
# emitting an unbounded table.
MAX_GROUPS = 20

# Non-substantive grouping codes to drop when the grouping column is not in the registry:
# the shared 7/8/9-family reserved codes plus the 96-99 and 996-999 "not ascertained /
# refused / don't know" bands NHIS uses for wider-range items.
_NONSUBSTANTIVE_GROUP_CODES = set(registry.NONSUBSTANTIVE_CODES) | {96} | set(range(996, 1000))


def _substantive_group_values(df: pd.DataFrame, groupby: str) -> list:
    """Ordered substantive values of a grouping column.

    Prefer the registry's `valid_codes` when the column is a known variable; otherwise take
    the distinct non-null values present, dropping the usual non-substantive codes (7/8/9,
    96-99, 996-999). Only integer-like categorical codes are kept, so grouping on a truly
    continuous column yields many values and trips the group cap rather than silently
    tabulating noise.
    """
    if groupby in registry.REGISTRY:
        present = set(df[groupby].dropna().unique())
        return [c for c in registry.get(groupby).valid_codes if c in present]
    values = []
    for v in sorted(df[groupby].dropna().unique()):
        f = float(v)
        if not f.is_integer():  # a non-integer value means this is not categorical
            continue
        iv = int(f)
        if iv in _NONSUBSTANTIVE_GROUP_CODES:
            continue
        values.append(iv)
    return values


@dataclass
class TableCell:
    """One group's weighted aggregate: the group value and its `SubpopulationResult`."""

    group_value: object
    result: SubpopulationResult


@dataclass
class TableResult:
    """A survey-weighted by-group table: one aggregate cell per substantive group value.

    Aggregate-only — every cell is a `SubpopulationResult` (estimate + design-based CI),
    never a set of individual rows.
    """

    variable: str
    groupby: str
    stat: str
    cells: list[TableCell]
    extra_universe: str | None = None
    q: float | None = None

    def summary(self) -> str:
        label = self.stat if self.q is None else f"{self.stat} (q={self.q:g})"
        weight_var = self.cells[0].result.weight_var if self.cells else registry.SAMPLE_ADULT_WEIGHT
        header = (
            f"{self.variable} {label} by {self.groupby} "
            f"(survey-weighted by {weight_var}"
        )
        if self.extra_universe:
            header += f"; universe: {self.extra_universe}"
        header += "):"
        lines = [header]
        for cell in self.cells:
            r = cell.result
            lines.append(
                f"  {self.groupby}={cell.group_value}: {r.estimate:.2f}{r.unit} "
                f"(95% CI {r.lci:.2f}-{r.uci:.2f}{r.unit}; n={r.unweighted_n})"
            )
        return "\n".join(lines)


def groupby_table(
    df: pd.DataFrame,
    variable: str,
    groupby: str,
    *,
    stat: str = "prevalence",
    q: float = 0.5,
    extra_universe: str | None = None,
) -> TableResult:
    """Survey-weighted aggregate + design-based CI for `variable` within each substantive
    value of the `groupby` column, assembled into a `TableResult`.

    Each cell reuses `subpopulation_stat` over the universe `(groupby == value)` combined
    (AND) with `extra_universe` when given, so no cell can drift from what `nhis analyze` /
    the single-cell tool return. Non-substantive group codes are dropped; empty groups (no
    substantive rows) are skipped rather than reported as a fabricated 0.0. Raises
    `ValueError` if the grouping column has more substantive values than `MAX_GROUPS`.
    """
    if groupby not in df.columns:
        raise ValueError(f"unknown grouping column: {groupby!r}")
    group_values = _substantive_group_values(df, groupby)
    if len(group_values) > MAX_GROUPS:
        raise ValueError(
            f"grouping column {groupby!r} has {len(group_values)} substantive values "
            f"(> cap {MAX_GROUPS}); groupby is for categorical columns, not near-continuous "
            f"ones"
        )
    cells: list[TableCell] = []
    for value in group_values:
        group_expr = f"({groupby} == {value})"
        universe = (
            f"{group_expr} & ({extra_universe})" if extra_universe else group_expr
        )
        try:
            res = subpopulation_stat(df, variable, universe_expr=universe, stat=stat, q=q)
        except ValueError:
            # Empty group (no substantive rows): skip rather than fabricate an estimate.
            continue
        cells.append(TableCell(group_value=value, result=res))
    if not cells:
        raise ValueError(
            f"no substantive groups for {variable!r} by {groupby!r}"
            + (f" within universe {extra_universe!r}" if extra_universe else "")
        )
    return TableResult(
        variable=variable, groupby=groupby, stat=stat, cells=cells,
        extra_universe=extra_universe, q=(q if stat == "quantile" else None),
    )


def fetch_microdata(dest_dir: str | Path = DATA_DIR) -> Path:
    """Download + unzip the NHIS 2023 Sample Adult public-use CSV (idempotent)."""
    import urllib.request

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    csv_path = dest_dir / "adult23.csv"
    if csv_path.exists():
        return csv_path
    zip_path = dest_dir / "adult23csv.zip"
    if not zip_path.exists():
        urllib.request.urlretrieve(NHIS_2023_ADULT_CSV_ZIP, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    if not csv_path.exists():
        raise RuntimeError(f"expected {csv_path} after unzip; archive layout changed")
    return csv_path
