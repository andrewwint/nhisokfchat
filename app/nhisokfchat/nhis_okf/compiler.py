"""Compile verified concepts into an Open Knowledge Format (OKF v0.1) bundle.

OKF v0.1 (Google Cloud, mid-2026) is a one-page, vendor-neutral spec: a bundle is a
directory of "concept" markdown files, each a YAML frontmatter block (only `type` is
required; `title`/`description`/`resource`/`tags`/`timestamp` recommended; unknown keys
tolerated) plus a markdown body, with relationships expressed as standard markdown links
and two reserved files, `index.md` (progressive navigation) and `log.md` (audit history).

This compiler emits a compliant bundle, and it is verified *by construction*: only concepts
that pass execution-grounded verification are written to `variables/`. A failing concept
(the seeded defect) is quarantined — it never enters the bundle — and its rejection is
recorded in `log.md` with the numbers. That is the difference between this bundle and a
passive RAG over the raw codebook.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from . import config, registry, trends as trends_mod
from .concepts import Concept, load_all
from .trends import TrendConcept, TrendVerifyResult
from .verify import VerifyResult, verify_all, PASS, FAIL, DESCRIPTIVE

REPO_ROOT = Path(__file__).resolve().parents[2]
# Bundle location resolves via config.okf_dir() (env `NHIS_OKF_DIR`, default repo-relative
# `.okf/`), so a packaged runtime reads its bundled copy. Retrieval imports VARIABLES_DIR
# from here; the env is read at import time (the runtime sets it before importing the agent).
OKF_DIR = config.okf_dir()
VARIABLES_DIR = OKF_DIR / "variables"
REFERENCES_DIR = OKF_DIR / "references"
# Hand-authored Reference concepts (part of the audit trail) copied into the bundle verbatim.
REFERENCE_SOURCES = REPO_ROOT / "concepts" / "references"
LOG_PATH = OKF_DIR / "log.md"
SOURCE = "NHIS 2023 Sample Adult public-use file (adult23.csv)"
RESOURCE = "https://www.cdc.gov/nchs/nhis/2023nhis.htm"
RESERVED = {"index.md", "log.md"}


@dataclass
class CompileReport:
    written: list[str]
    quarantined: list[str]
    results: list[VerifyResult]
    trend_written: list[str] = field(default_factory=list)
    trend_quarantined: list[str] = field(default_factory=list)
    trend_results: list[TrendVerifyResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        # A clean compile catches every seeded defect and writes every sound concept.
        all_results = list(self.results) + list(self.trend_results)
        for r in all_results:
            if r.seeded_defect and r.verdict != FAIL:
                return False
            if not r.seeded_defect and r.verdict == FAIL:
                return False
        return True


# --- helpers --------------------------------------------------------------------------

def _description(concept: Concept) -> str:
    if concept.is_analytical and concept.statistic:
        text = concept.statistic
    else:
        # First sentence of the prose for descriptive concepts.
        first = concept.prose.strip().split(". ")[0].strip()
        text = (first.rstrip(".") + ".") if first else concept.label
    # Single line, links resolved to markdown, quote-safe for the YAML scalar.
    text = _wikilinks_to_markdown(" ".join(text.split()))
    return text.replace('"', "'")


def _tags(concept: Concept) -> list[str]:
    tags = ["nhis-2023", "diabetes", concept.variable]
    if concept.is_analytical:
        tags.append(concept.kind)
    return tags


def _wikilinks_to_markdown(text: str) -> str:
    """Convert `[[ID]]` prose wikilinks to spec-standard relative markdown links."""
    return re.sub(r"\[\[([A-Za-z0-9_]+)\]\]", r"[\1](./\1.md)", text)


def _yaml_list(items) -> str:
    return "[" + ", ".join(items) + "]" if items else "[]"


def _frontmatter(concept: Concept, r: VerifyResult, ts: str) -> str:
    var = registry.get(concept.variable)
    # Recommended OKF fields first; `type` is the only required one.
    lines = [
        "---",
        "type: variable_definition",
        f'title: "{concept.label}"',
        f'description: "{_description(concept)}"',
        f'resource: "{RESOURCE}"',
        f"tags: {_yaml_list(_tags(concept))}",
        f'timestamp: "{ts}"',
        "# extension keys (OKF consumers tolerate unknown fields)",
        f"id: {concept.id}",
        f"variable: {concept.variable}",
        f'question_universe: "{var.universe_text}"',
    ]
    if concept.analytical_universe:
        lines.append(f'analytical_universe: "{concept.analytical_universe}"')
    lines.append(f"weight: {var.weight}")
    lines.append(f'source: "{SOURCE}"')
    if concept.is_analytical:
        lines.append(f'statistic: "{concept.statistic}"')
        if concept.kind == "prevalence":
            lines.append(f"value_pct: {r.correct_pct}")
        else:
            # Units-aware value for mean/quantile (years, not a percentage).
            lines += [f"kind: {concept.kind}", f"value: {r.correct_pct}",
                      f'unit: "{concept.unit}"']
            if concept.quantile_q is not None:
                lines.append(f"quantile_q: {concept.quantile_q}")
    lines += [
        "verification:",
        f"  verdict: {r.verdict}",
        "  method: execution-grounded",
    ]
    if concept.is_analytical:
        lines += [
            f"  correct_pct: {r.correct_pct}",
            f"  claimed_pct: {r.claimed_pct}",
            f"  delta_pp: {r.delta_pp}",
            f'  detail: "{r.correct_detail}"',
        ]
        if r.ci is not None:
            lines += [
                f"  ci_95: [{r.ci.lci_pct:.2f}, {r.ci.uci_pct:.2f}]",
                f"  se_pp: {r.ci.se_pp:.2f}",
                f"  deff: {r.ci.deff:.2f}",
                "  variance_method: taylor-linearization (design-based)",
            ]
    lines += [f"  verified_at: {ts}", "---"]
    return "\n".join(lines)


def _reproduce_block(concept: Concept) -> list[str]:
    """The exact `nhis analyze` (weighted, verified) and `nhis rows` (raw inspection)
    invocations that reproduce an analytical concept's figure, over its analytical universe.

    Both modes are deterministic: `nhis analyze` re-derives the cited survey-weighted
    aggregate; `nhis rows` shows a few of the underlying records for a sanity check. See the
    [tool reference](../references/parquet_query.md) for the two-mode retrieval model.
    """
    var = registry.get(concept.variable)
    universe = concept.analytical_universe or var.universe_expr

    analyze = f"nhis analyze --variable {concept.variable}"
    if universe:
        analyze += f' --universe "{universe}"'
    if concept.kind != "prevalence":
        analyze += f" --stat {concept.kind}"
        if concept.kind == "quantile" and concept.quantile_q is not None:
            analyze += f" --q {concept.quantile_q:g}"

    # A few columns for row inspection: the variable plus whatever the universe references.
    cols = [t for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", universe or "")]
    cols = list(dict.fromkeys([*cols, concept.variable]))
    rows = f'nhis rows --columns "{",".join(cols)}"'
    if universe:
        rows += f' --universe "{universe}"'
    rows += " --limit 10"

    return [
        "## Reproduce",
        "",
        "Weighted, verified figure (aggregate only — the number to cite):",
        "",
        "```bash",
        analyze,
        "```",
        "",
        "Raw row inspection (unweighted, not verified — for sanity-checking only; see the "
        "[tool reference](../references/parquet_query.md)):",
        "",
        "```bash",
        rows,
        "```",
        "",
    ]


def _body(concept: Concept, r: VerifyResult) -> str:
    parts = [f"# {concept.label}", "", _wikilinks_to_markdown(concept.prose), ""]
    if concept.is_analytical:
        if concept.kind == "prevalence":
            value_str = f"{r.correct_pct}%"
        else:
            value_str = f"{r.correct_pct} {concept.unit}".strip()
        parts += [
            "## Verified statistic",
            "",
            f"**{concept.statistic}: {value_str}**",
            "",
        ]
        if r.ci is not None:
            parts.append(
                f"- 95% CI: [{r.ci.lci_pct:.2f}, {r.ci.uci_pct:.2f}] "
                f"(design-based, Taylor linearization; SE {r.ci.se_pp:.2f}pp; "
                f"DEFF {r.ci.deff:.2f})"
            )
        parts += [
            f"- Basis: {r.correct_detail}",
            f"- Verification: executed against {SOURCE}; verdict **{r.verdict}**.",
            "",
        ]
        parts += _reproduce_block(concept)
    if concept.links:
        parts.append("## Related")
        parts += [f"- [{l}](./{l}.md)" for l in concept.links]
        parts.append("")
    return "\n".join(parts)


def render_concept(concept: Concept, r: VerifyResult, ts: str) -> str:
    return _frontmatter(concept, r, ts) + "\n\n" + _body(concept, r)


def _render_trend(concept: TrendConcept, r: TrendVerifyResult, ts: str) -> str:
    years_csv = ", ".join(str(y) for y in concept.years)
    vals = "{" + ", ".join(f"{y}: {r.correct.get(y)}" for y in concept.years) + "}"
    fm = [
        "---",
        "type: metric",
        f'title: "{concept.title}"',
        f'description: "{concept.statistic}"',
        f'resource: "{RESOURCE}"',
        f"tags: [nhis, diabetes, trend, {years_csv}]",
        f'timestamp: "{ts}"',
        "# extension keys (OKF consumers tolerate unknown fields)",
        f"id: {concept.id}",
        f"canonical: {concept.canonical}",
        f"years: [{years_csv}]",
        "method: per-year-variable (rename-aware across the 2019 redesign)",
        f"values_pct: {vals}",
        "verification:",
        f"  verdict: {r.verdict}",
        "  method: execution-grounded (cross-year)",
        f"  correct_pct: {vals}",
        f"  verified_at: {ts}",
        f"links: {_yaml_list(concept.links)}",
        "---",
    ]
    body = [
        f"# {concept.title}",
        "",
        _wikilinks_to_markdown(concept.prose),
        "",
        "## Verified trend",
        "",
    ]
    body += [f"- {y}: {r.correct.get(y)}%" for y in concept.years]
    body += [
        "",
        f"- Verification: each year executed against its own file with its own weight; "
        f"verdict **{r.verdict}**.",
        "",
    ]
    if concept.links:
        body.append("## Related")
        body += [f"- [{l}](./{l}.md)" for l in concept.links]
        body.append("")
    return "\n".join(fm) + "\n\n" + "\n".join(body)


def _trend_years_available(trend_list: list[TrendConcept]) -> bool:
    needed = {y for c in trend_list for y in c.years}
    return all(trends_mod.year_csv(y).exists() for y in needed)


def _render_index(written: list[Concept], ts: str, trend_ids: list[str] | None = None) -> str:
    lines = [
        "---",
        "type: index",
        'title: "NHIS 2023 diabetes — verified OKF bundle"',
        'description: "Execution-verified NHIS 2023 diabetes concepts; progressive entry point."',
        f'timestamp: "{ts}"',
        "---",
        "",
        "# NHIS 2023 diabetes — verified OKF bundle",
        "",
        "Concepts below passed execution-grounded verification (survey-weighted, "
        "universe-correct). See [log.md](log.md) for the full audit history, including "
        "any quarantined concepts.",
        "",
    ]
    for c in written:
        lines.append(f"- [variables/{c.id}](variables/{c.id}.md) — {_description(c)}")
    if trend_ids:
        lines.append("")
        lines.append("## Cross-year trends")
        for tid in trend_ids:
            lines.append(f"- [variables/{tid}](variables/{tid}.md)")
    lines.append("")
    return "\n".join(lines)


def _write_log(
    results: list[VerifyResult],
    ts: str,
    log_path: Path = LOG_PATH,
    trend_results: list[TrendVerifyResult] | None = None,
) -> None:
    lines = [
        "# OKF audit log",
        "",
        f"Compiled from {SOURCE}.",
        f"Last run: {ts}",
        "",
        "Every concept is verified by *executing* its analysis against the real microdata",
        "with proper survey weights — not by checking links. Quarantined concepts failed",
        "that check and were kept out of the trusted bundle.",
        "",
        "| concept | verdict | claimed | correct | delta (pp) | note |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in results:
        claimed = "—" if r.claimed_pct is None else f"{r.claimed_pct}"
        correct = "—" if r.correct_pct is None else f"{r.correct_pct}"
        delta = "—" if r.delta_pp is None else f"{r.delta_pp}"
        note = ""
        if r.verdict == FAIL:
            note = "; ".join(r.diagnosis) or "claim does not match executed result"
            if r.caught:
                note = "QUARANTINED — lint passed, execution caught it: " + note
        elif r.verdict == DESCRIPTIVE:
            note = "documented (no executable statistic)"
        lines.append(
            f"| {r.concept_id} | {r.verdict} | {claimed} | {correct} | {delta} | {note} |"
        )
    if trend_results:
        lines += [
            "",
            "## Cross-year trends (2019 redesign-rename catch)",
            "",
            "| trend | verdict | note |",
            "| --- | --- | --- |",
        ]
        for r in trend_results:
            note = ""
            if r.verdict == FAIL:
                note = "; ".join(r.diagnosis)
                if r.caught:
                    note = "QUARANTINED — lint passed, execution caught it: " + note
            lines.append(f"| {r.concept_id} | {r.verdict} | {note} |")
    lines.append("")
    log_path.write_text("\n".join(lines))


def _emit_references(bundle_root: Path, source_dir: Path = REFERENCE_SOURCES) -> list[str]:
    """Copy hand-authored Reference concepts into `<bundle>/references/` verbatim."""
    if not source_dir.exists():
        return []
    refs_dir = bundle_root / "references"
    refs_dir.mkdir(parents=True, exist_ok=True)
    for old in refs_dir.glob("*.md"):  # start clean, mirroring the source dir
        old.unlink()
    written = []
    for src in sorted(source_dir.glob("*.md")):
        (refs_dir / src.name).write_text(src.read_text())
        written.append(f"references/{src.stem}")
    return written


def compile_bundle(
    df: pd.DataFrame,
    concept_list: list[Concept] | None = None,
    *,
    out_dir: Path = VARIABLES_DIR,
    log_path: Path = LOG_PATH,
) -> CompileReport:
    """Compile to `out_dir` (the bundle's `variables/`). Reserved `index.md` and `log.md`
    go in the bundle root (`out_dir.parent`). Tests pass a temp dir so running the suite
    never dirties the committed `.okf/` artifact."""
    concept_list = concept_list or load_all()
    results = verify_all(df, concept_list)
    by_id = {c.id: c for c in concept_list}

    out_dir = Path(out_dir)
    bundle_root = out_dir.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.md"):  # start clean; no lingering quarantined concepts
        old.unlink()

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    written, quarantined, written_concepts = [], [], []
    for r in results:
        concept = by_id[r.concept_id]
        if r.verdict == FAIL:
            quarantined.append(r.concept_id)
            continue
        (out_dir / f"{concept.id}.md").write_text(render_concept(concept, r, ts))
        written.append(concept.id)
        written_concepts.append(concept)

    # Cross-year trends — only when every required year's file is present (so a 2023-only
    # checkout or CI without the 2018 fetch still compiles cleanly).
    trend_written, trend_quarantined, trend_results = [], [], []
    trend_list = trends_mod.load_trends()
    if trend_list and _trend_years_available(trend_list):
        trend_results = trends_mod.verify_all_trends(trend_list)
        t_by_id = {c.id: c for c in trend_list}
        for r in trend_results:
            if r.verdict == FAIL:
                trend_quarantined.append(r.concept_id)
                continue
            (out_dir / f"{r.concept_id}.md").write_text(
                _render_trend(t_by_id[r.concept_id], r, ts)
            )
            trend_written.append(r.concept_id)

    # Reference concepts (hand-authored tool docs) are copied verbatim into the bundle so a
    # reader/agent is mapped to the researcher row tool. They are part of the audit trail
    # (versioned under concepts/references/) and normal OKF concept docs, not reserved files.
    _emit_references(bundle_root)

    (bundle_root / "index.md").write_text(
        _render_index(written_concepts, ts, trend_ids=trend_written)
    )
    _write_log(results, ts, log_path, trend_results=trend_results)
    return CompileReport(
        written=written,
        quarantined=quarantined,
        results=results,
        trend_written=trend_written,
        trend_quarantined=trend_quarantined,
        trend_results=trend_results,
    )


# --- OKF v0.1 conformance --------------------------------------------------------------

def _split_frontmatter(raw: str) -> dict | None:
    m = re.match(r"^---\n(.*?)\n---\n", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = yaml.safe_load(m.group(1))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def check_conformance(bundle_root: Path = OKF_DIR) -> tuple[bool, list[str]]:
    """Check a bundle against the OKF v0.1 conformance matrix:
    1. every non-reserved .md parses to valid YAML frontmatter,
    2. `type` is present on every concept,
    3. reserved files (index.md/log.md), if present, are structured.
    """
    bundle_root = Path(bundle_root)
    issues: list[str] = []
    concepts = [p for p in bundle_root.rglob("*.md") if p.name not in RESERVED]
    if not concepts:
        issues.append("no concept files found")
    for p in concepts:
        fm = _split_frontmatter(p.read_text())
        rel = p.relative_to(bundle_root)
        if fm is None:
            issues.append(f"{rel}: missing or invalid YAML frontmatter")
        elif "type" not in fm or not fm["type"]:
            issues.append(f"{rel}: missing required 'type' field")
    for reserved in ("index.md", "log.md"):
        if not (bundle_root / reserved).exists():
            issues.append(f"missing reserved {reserved}")
    return (not issues, issues)
