"""Plumbing for the grounded chat agent — everything that isn't the prompt or a tool.

`chat.py` holds the three things a reader cares about (the system prompt and the two
tool-logic functions); `main.py` assembles and serves the agent. This module is the
low-level machinery both lean on: retrieval + answer formatting, the survey-weighted
microdata loader, the universe injection-gate, and the Bedrock model builder.

Nothing here is agent-facing, and to keep the imports acyclic this module imports neither
`chat` nor `main` (they import it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from . import config
from .retrieval import Retriever, Hit

SAFETY = (
    "This tool explores public, de-identified, aggregate survey data (CDC NHIS 2023). "
    "It is not medical advice and makes no individual-level inference. Every figure is "
    "survey-weighted and cited to its source variable. It reads only verified aggregate "
    "concepts — never individual survey records."
)

# Per-invocation cost guardrails (the public endpoint has no auth — these bound spend).
# Output is hard-capped at the model; input is length-limited; one grounded answer per call.
MAX_OUTPUT_TOKENS = 600
MAX_QUESTION_CHARS = 600


@dataclass
class Answer:
    text: str
    mode: str  # "extractive" | "generative" | "rejected"
    citations: list[str] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)


# --- Retrieval + formatting (used by tool_search_okf and the extractive answer) ----------

def retrieve(query: str, k: int = 3) -> list[Hit]:
    """The k verified concepts most relevant to `query`, over the shipped OKF bundle."""
    return Retriever.from_bundle().search(query, k=k)


def _citation(hit: Hit) -> str:
    fm = hit.concept.frontmatter
    src = fm.get("source", "NHIS 2023 Sample Adult")
    return f"{hit.concept.id} ({src})"


def format_hits(hits: list[Hit]) -> str:
    """Render retrieved verified concepts for the agent. NO_VERIFIED_CONCEPTS_FOUND if empty."""
    if not hits:
        return "NO_VERIFIED_CONCEPTS_FOUND"
    blocks = []
    for h in hits:
        fm = h.concept.frontmatter
        stat = fm.get("statistic")
        val = fm.get("value_pct")
        detail = (fm.get("verification") or {}).get("detail", "")
        line = f"[{h.concept.id}] {h.concept.label}"
        if stat and val is not None:
            line += f"\n  {stat}: {val}% ({detail})"
        else:
            line += f"\n  {h.concept.text.splitlines()[0] if h.concept.text else ''}"
        blocks.append(line)
    return "\n\n".join(blocks)


# --- The microdata + the universe injection-gate (used by tool_analyze_rows) -------------

@lru_cache(maxsize=1)
def microdata():
    """The slim NHIS microdata, loaded once per process for the query-time tool.

    Prefers the shipped parquet (only the columns the verified variables + survey design
    need), so this is cheap. An ad-hoc universe may reference any of those columns.
    """
    from . import analysis

    return analysis.load_microdata(config.microdata_path())


def agent_allowed_columns():
    """The real microdata columns an agent universe may reference (the allow-list source).

    Read from the shipped parquet's schema (cheap, no data load) so identifiers are
    validated against actual columns, not a hardcoded list.
    """
    from . import analysis

    return analysis.table_columns(config.microdata_path())


def validate_agent_universe(universe: str | None) -> None:
    """Gate an agent-supplied universe through the allow-list before ANY df.eval.

    Raises ValueError (never evaluates) for anything outside `COLUMN <op> NUMBER` joined by
    `& | ( )` over known columns. This is the `injection-sink@universe-eval` mitigation for
    the `tool_analyze_rows` tool, which reaches `analysis._mask`'s df.eval.
    """
    if not universe:
        return
    from . import analysis

    analysis.validate_universe(universe, agent_allowed_columns())


# --- The extractive fallback (grounded answer when the Bedrock agent is unavailable) -----

def extractive_answer(query: str, hits: list[Hit]) -> Answer:
    """A grounded answer built directly from the top retrieved concept — no model needed.

    This is `main.invoke`'s fallback when the Bedrock agent errors (e.g. no credentials), so
    the deploy still returns a cited, verified figure rather than failing the request.
    """
    if not hits:
        return Answer(
            text=f"No verified concept matches that question.\n\n{SAFETY}",
            mode="extractive",
        )
    top = hits[0]
    fm = top.concept.frontmatter
    stat = fm.get("statistic")
    value = fm.get("value_pct")
    if stat and value is not None:
        body = f"{stat}: {value}%."
        detail = (fm.get("verification") or {}).get("detail")
        if detail:
            body += f" ({detail})"
    else:
        first = top.concept.text.splitlines()[0] if top.concept.text else ""
        body = f"{top.concept.label}: {first}"
    cites = [_citation(h) for h in hits]
    return Answer(
        text=f"{body}\n\nSource: {cites[0]}\n\n{SAFETY}",
        mode="extractive",
        citations=cites,
        hits=hits,
    )
