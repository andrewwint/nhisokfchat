"""Command-line interface: fetch, compile, verify, query.

    python -m nhis_okf fetch      # download the NHIS 2023 public-use file
    python -m nhis_okf compile    # verify concepts and emit the OKF bundle
    python -m nhis_okf verify     # run execution-grounded verification, print verdicts
    python -m nhis_okf query "how many adults with diabetes take insulin?"
"""

from __future__ import annotations

import argparse
import sys

from . import (
    analysis,
    concepts as concepts_mod,
    verify as verify_mod,
    trends as trends_mod,
    registry,
    parquet_query,
)
from .compiler import compile_bundle, check_conformance, OKF_DIR
from .retrieval import verified_variables

SAFETY = (
    "Public, de-identified, aggregate CDC NHIS survey data — not medical advice, no "
    "individual-level inference. Every figure is survey-weighted and design-based."
)

# Printed before every `nhis rows` result. Raw rows are the one non-aggregate surface, so
# the caveat is mandatory and loud: these records are not a population estimate.
ROWS_CAVEAT = (
    "=" * 78 + "\n"
    "RAW MICRODATA ROWS — NOT a population estimate, NOT verified.\n"
    "These are individual, UNWEIGHTED records from the public-use, de-identified NHIS\n"
    "file, shown for research inspection only. Without survey weights they do NOT\n"
    "estimate the U.S. population — do not read a rate or count off of them.\n"
    "For a weighted, verified figure use `nhis analyze`.\n"
    + "=" * 78
)

# Columns the diabetes slice needs (keeps the 29MB load fast).
SLICE_COLUMNS = [
    "DIBEV_A", "DIBINS_A", "DIBPILL_A", "DIBAGETC_A", "PREDIB_A", "GESDIB_A",
    "HYPEV_A", "HYPMED_A",
    "WEIGHTLBTC_A", "HEIGHTTC_A", "BMICAT_A", "SEX_A",
    "WTFA_A", "PSTRAT", "PPSU",
]


def _load_df():
    return analysis.load_microdata(columns=SLICE_COLUMNS)


def cmd_fetch(_args) -> int:
    for year in sorted(registry.YEAR_FILES):
        path = trends_mod.fetch_year(year)
        twin = analysis.materialize_parquet(path)  # derived columnar cache (idempotent)
        print(f"microdata ready ({year}): {path}")
        print(f"  parquet twin: {twin}")
    return 0


def cmd_build(_args) -> int:
    """(Re)materialize the parquet twin next to each fetched CSV."""
    for year in sorted(registry.YEAR_FILES):
        csv_path = trends_mod.year_csv(year)
        if not csv_path.exists():
            print(f"skip {year}: {csv_path} not fetched")
            continue
        twin = analysis.materialize_parquet(csv_path, force=True)
        print(f"parquet built ({year}): {twin}")
    return 0


def _verified_variables() -> set[str]:
    """Variables backed by a verified concept in the compiled bundle.

    Thin wrapper over the shared `retrieval.verified_variables` allow-list, which the
    agent's `analyze_subpopulation` tool reuses so both surfaces gate on the same set.
    """
    return verified_variables()


def cmd_analyze(args) -> int:
    # Grounded-or-refuse: only variables the verification gate saw and passed.
    verified = _verified_variables()
    if args.variable not in verified:
        print(
            f"refused: {args.variable!r} is not backed by a verified concept in the "
            f"compiled bundle. Run `nhis compile` first, or choose one of: "
            f"{', '.join(sorted(verified)) or '(none compiled)'}.",
            file=sys.stderr,
        )
        return 2
    df = _load_df()
    if args.groupby:
        # By-group weighted table: one aggregate cell per substantive group value, no rows.
        try:
            table = analysis.groupby_table(
                df, args.variable, args.groupby, stat=args.stat, q=args.q,
                extra_universe=args.universe,
            )
        except Exception as exc:
            print(f"could not compute: {exc}", file=sys.stderr)
            return 1
        print(table.summary())
        print(f"\n{SAFETY}")
        return 0
    try:
        res = analysis.subpopulation_stat(
            df, args.variable, universe_expr=args.universe, stat=args.stat, q=args.q
        )
    except Exception as exc:
        print(f"could not compute: {exc}", file=sys.stderr)
        return 1
    # Aggregate only — the point estimate and its CI, never any individual rows.
    print(res.summary())
    print(f"\n{SAFETY}")
    return 0


def cmd_trends(_args) -> int:
    results = trends_mod.verify_all_trends()
    caught = 0
    for r in results:
        line = f"[{r.verdict:5}] {r.concept_id}  correct={r.correct}"
        print(line)
        for d in r.diagnosis:
            print(f"    - {d}")
        if r.caught:
            caught += 1
            print("    ^ caught by EXECUTION (the lint passed)")
    print(f"\n{caught} cross-year defect(s) caught by execution-grounded verification.")
    real_failures = [
        r for r in results if r.verdict == trends_mod.FAIL and not r.seeded_defect
    ]
    return 1 if real_failures else 0


def cmd_verify(_args) -> int:
    df = _load_df()
    results = verify_mod.verify_all(df, concepts_mod.load_all())
    caught = 0
    for r in results:
        head = f"[{r.verdict:11}] {r.concept_id}"
        if r.claimed_pct is not None:
            u = "%" if r.unit == "%" else f" {r.unit}"
            head += f"  claimed={r.claimed_pct}{u}  correct={r.correct_pct}{u}  Δ={r.delta_pp}{u if u.strip() else ' pp'}"
        print(head)
        for d in r.diagnosis:
            print(f"    - {d}")
        if r.caught:
            caught += 1
            print("    ^ caught by EXECUTION (the lint passed)")
    print(f"\n{caught} defect(s) caught by execution-grounded verification.")
    # Non-zero exit if a non-seeded concept failed (a real regression).
    real_failures = [
        r for r in results if r.verdict == verify_mod.FAIL and not r.seeded_defect
    ]
    return 1 if real_failures else 0


def cmd_compile(_args) -> int:
    df = _load_df()
    report = compile_bundle(df)
    print(f"written to .okf/variables/: {report.written}")
    print(f"quarantined (failed verification): {report.quarantined}")
    if report.trend_results:
        print(f"trends written: {report.trend_written}")
        print(f"trends quarantined: {report.trend_quarantined}")
    print(f"audit log: .okf/log.md")
    if not report.ok:
        print("WARNING: compile invariant violated (a seeded defect passed or a sound "
              "concept failed).", file=sys.stderr)
        return 1
    return 0


def cmd_conformance(_args) -> int:
    ok, issues = check_conformance(OKF_DIR)
    if ok:
        print("OKF v0.1 conformance: PASS")
        return 0
    print("OKF v0.1 conformance: FAIL")
    for i in issues:
        print(f"    - {i}")
    return 1


def cmd_rows(args) -> int:
    # Researcher tool: the ONE surface that returns raw individual rows (see parquet_query).
    columns = [c.strip() for c in (args.columns or "").split(",") if c.strip()]
    if not columns:
        print(
            "refused: --columns is required and must name at least one column "
            "(no accidental full-width dump).",
            file=sys.stderr,
        )
        return 2
    try:
        rows = parquet_query.query_rows(
            columns, universe_expr=args.universe, limit=args.limit
        )
    except Exception as exc:
        print(f"could not query rows: {exc}", file=sys.stderr)
        return 1
    # Loud caveat header on EVERY call, printed BEFORE the rows.
    print(ROWS_CAVEAT)
    print()
    print(rows.to_string(index=False))
    effective = min(args.limit, parquet_query.HARD_MAX_LIMIT)
    print(f"\n{len(rows)} row(s) shown (limit {effective}, hard max "
          f"{parquet_query.HARD_MAX_LIMIT}).")
    return 0


def cmd_query(args) -> int:
    from .chat import answer

    ans = answer(args.question)
    print(f"[{ans.mode}] {ans.text}")
    if ans.citations:
        print(f"\ncitations: {', '.join(ans.citations)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="nhis", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch", help="download the NHIS 2023 public-use file")
    sub.add_parser("build", help="(re)materialize the parquet twin next to each CSV")
    sub.add_parser("compile", help="verify concepts and emit the OKF bundle")
    sub.add_parser("verify", help="run execution-grounded verification")
    sub.add_parser("conformance", help="check the bundle against the OKF v0.1 spec")
    sub.add_parser("trends", help="verify cross-year trends (the 2019 redesign-rename catch)")
    q = sub.add_parser("query", help="ask a question grounded in the verified bundle")
    q.add_argument("question")
    a = sub.add_parser(
        "analyze",
        help="survey-weighted aggregate + design CI for a subpopulation (aggregate only)",
    )
    a.add_argument("--variable", required=True, help="a variable backed by a verified concept")
    a.add_argument(
        "--universe", default=None,
        help="pandas row filter defining the subpopulation, e.g. 'DIBEV_A == 1'",
    )
    a.add_argument(
        "--groupby", default=None,
        help="categorical column to tabulate by, e.g. 'SEX_A'; prints one weighted "
        "aggregate cell (estimate + design CI) per substantive group value, no rows",
    )
    a.add_argument(
        "--stat", default="prevalence", choices=["prevalence", "mean", "quantile"],
    )
    a.add_argument("--q", type=float, default=0.5, help="quantile probability (for --stat quantile)")
    r = sub.add_parser(
        "rows",
        help="researcher tool: RAW, UNWEIGHTED public-use rows (a few columns) — not "
        "verified, not a population estimate; use `nhis analyze` for weighted figures",
    )
    r.add_argument(
        "--columns", required=True,
        help=f"comma-separated column list (required; at most "
        f"{parquet_query.MAX_COLUMNS}), e.g. 'DIBEV_A,DIBINS_A,SEX_A'",
    )
    r.add_argument(
        "--universe", default=None,
        help="optional pandas row filter, e.g. 'DIBEV_A == 1'",
    )
    r.add_argument(
        "--limit", type=int, default=parquet_query.DEFAULT_LIMIT,
        help=f"max rows to show (default {parquet_query.DEFAULT_LIMIT}, hard max "
        f"{parquet_query.HARD_MAX_LIMIT})",
    )
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return {
        "fetch": cmd_fetch,
        "build": cmd_build,
        "compile": cmd_compile,
        "verify": cmd_verify,
        "conformance": cmd_conformance,
        "trends": cmd_trends,
        "query": cmd_query,
        "analyze": cmd_analyze,
        "rows": cmd_rows,
    }[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
