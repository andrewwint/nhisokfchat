"""Researcher row-level query tool over the public-use NHIS microdata.

This is deliberately the ONE surface in the project that returns individual **rows**
rather than a survey-weighted aggregate. That is safe here, and only here, because NHIS
public-use files are de-identified and top-coded precisely so row inspection is their
intended use — but the returned records are RAW and UNWEIGHTED, so they are never a
population estimate. The verified path (`nhis analyze`, grounded-or-refuse) and the
deployed grounded agent (`chat.py`, `agentcore_app.py`) stay aggregate-only and MUST NOT
import this module. Keep that boundary intact.

The tool requires an explicit column list (no accidental full-width dump) and bounds the
row count (no accidental full-length dump), so an inspection stays a deliberate, scoped
lookup rather than an export firehose.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from . import analysis

# Row caps: a small default so a bare invocation returns an inspectable handful, and a hard
# ceiling so `--limit` can never turn the tool into a bulk exporter.
DEFAULT_LIMIT = 20
HARD_MAX_LIMIT = 500

# Column cap: this tool pulls a FEW columns cheaply from the columnar parquet — never a
# wide/full-width dump. Requesting more than this errors.
MAX_COLUMNS = 12


def _expr_columns(expr: str | None) -> list[str]:
    """Identifier-shaped tokens in a universe expression (its referenced columns).

    NHIS universe expressions use symbolic operators (`==`, `&`, `|`, parentheses) and
    numeric literals, so the identifier tokens are the column names. Extra tokens are
    harmless: `analysis.load_table` intersects the projection with the columns actually
    present, so anything that is not a real column is silently dropped.
    """
    if not expr:
        return []
    return list(dict.fromkeys(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr)))


def query_rows(
    columns,
    *,
    universe_expr: str | None = None,
    limit: int = DEFAULT_LIMIT,
    csv_path: str | Path = analysis.DEFAULT_CSV,
) -> pd.DataFrame:
    """Return the requested `columns` of the rows matching `universe_expr`, up to `limit`.

    This intentionally returns individual records — that is the tool's purpose. It requires
    an explicit, non-empty `columns` list (no accidental full dump) and clamps `limit` to
    `HARD_MAX_LIMIT`. Loading goes through the parquet-preferring `analysis.load_table`, and
    the universe filter reuses `analysis._mask` (see its `df.eval` trust-boundary note:
    `universe_expr` is CLI-supplied, local, and trusted).
    """
    columns = [c for c in (columns or []) if c]
    if not columns:
        raise ValueError(
            "query_rows requires an explicit non-empty column list — refusing to dump "
            "every column of the microdata."
        )
    if len(columns) > MAX_COLUMNS:
        raise ValueError(
            f"too many columns ({len(columns)}): request at most {MAX_COLUMNS} — this "
            f"tool pulls a few columns for inspection, not a wide dump."
        )
    if limit < 1:
        raise ValueError(f"limit must be >= 1, got {limit}")
    limit = min(limit, HARD_MAX_LIMIT)

    # Load only the requested columns plus any the universe filter references.
    needed = list(dict.fromkeys([*columns, *_expr_columns(universe_expr)]))
    df = analysis.load_table(csv_path, columns=needed)

    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"unknown column(s) not present in the microdata: {missing}")

    mask = analysis._mask(df, universe_expr)
    # Project to exactly the requested columns (in the requested order), capped.
    return df.loc[mask, columns].head(limit).reset_index(drop=True)
