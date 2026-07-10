"""Local RAG retrieval over the verified OKF bundle.

Deliberately local and dependency-light: TF-IDF + cosine over the compiled
`.okf/variables/*.md` concepts. No embedding-model download, no API key, no network —
fits the local-first / data-residency posture. Swapping in sentence-transformer
embeddings is a documented upgrade path, not a requirement for the slice.

The retrieval corpus is the *verified* bundle only. A quarantined concept (the naive
insulin figure) is never written to `.okf/variables/`, so it cannot be retrieved or
served. Verification at compile time is what makes retrieval trustworthy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import config

# Resolve the bundle location from config (env `NHIS_OKF_DIR`, default repo-relative `.okf/`)
# rather than from `compiler` — importing `compiler` here would drag pandas into the
# retrieval-only runtime path, which must stay pandas-free.
VARIABLES_DIR = config.okf_dir() / "variables"


@dataclass
class OkfConcept:
    id: str
    label: str
    text: str
    frontmatter: dict
    path: Path


@dataclass
class Hit:
    concept: OkfConcept
    score: float


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.DOTALL)
    if not m:
        return {}, raw
    return yaml.safe_load(m.group(1)) or {}, m.group(2).strip()


def load_bundle(variables_dir: Path = VARIABLES_DIR) -> list[OkfConcept]:
    out: list[OkfConcept] = []
    for p in sorted(Path(variables_dir).glob("*.md")):
        raw = p.read_text()
        fm, body = _split_frontmatter(raw)
        out.append(
            OkfConcept(
                id=fm.get("id", p.stem),
                label=fm.get("title") or fm.get("label") or p.stem,
                text=body,
                frontmatter=fm,
                path=p,
            )
        )
    return out


class Retriever:
    def __init__(self, concepts: list[OkfConcept]):
        if not concepts:
            raise ValueError(
                "OKF bundle is empty. Run `nhis compile` before querying."
            )
        self.concepts = concepts
        # Index label + body so a query like "insulin" matches both.
        corpus = [f"{c.label}\n{c.text}" for c in concepts]
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.matrix = self.vectorizer.fit_transform(corpus)

    def search(self, query: str, k: int = 3) -> list[Hit]:
        qv = self.vectorizer.transform([query])
        sims = cosine_similarity(qv, self.matrix)[0]
        ranked = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)
        return [Hit(self.concepts[i], float(sims[i])) for i in ranked[:k] if sims[i] > 0]

    @classmethod
    def from_bundle(cls, variables_dir: Path = VARIABLES_DIR) -> "Retriever":
        return cls(load_bundle(variables_dir))


def verified_variables(variables_dir: Path = VARIABLES_DIR) -> set[str]:
    """Variables backed by a verified concept in the compiled bundle.

    The compiler only writes concepts that passed execution-grounded verification, so a
    concept file's presence is proof of grounding. This is the shared allow-list for both
    the `nhis analyze` CLI and the agent's `analyze_subpopulation` tool.
    """
    return {
        c.frontmatter["variable"]
        for c in load_bundle(variables_dir)
        if c.frontmatter.get("variable")
    }
