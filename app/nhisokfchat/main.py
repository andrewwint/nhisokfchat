"""AgentCore Runtime entrypoint — the whole grounded agent, assembled and served here.

Open this file to see the entire deployed surface at a glance:

  * the two `@tool`s the agent can call (thin wrappers over `chat.search_okf` /
    `chat.analyze_rows` — both aggregate-only, neither ever returns individual rows),
  * the Strands `Agent` on Amazon Bedrock, built lazily on first use, and
  * `invoke`, the `POST /invocations` entrypoint: it retrieves grounding, runs the agent,
    and falls back to a cited extractive answer if Bedrock is unavailable.

Everything it leans on lives in two nearby modules: the prompt + tool logic in
`nhis_okf/chat.py`, and the plumbing (retrieval, formatting, the microdata loader, the
universe injection-gate, the model builder) in `nhis_okf/helpers.py`.

Grounded-or-refuse and aggregate-only by construction: `tool_search_okf` reads only the
verified OKF bundle (`nhis_okf/okf_bundle/`), and `tool_analyze_rows` computes a
survey-weighted subgroup figure over the slim NHIS parquet (`nhis_okf/microdata/`),
restricted to verified variables with its universe allow-list-validated before any
`df.eval`. There is no raw-row tool, so there is no row path. `BedrockAgentCoreApp`
provides `GET /ping` (liveness) and maps `invoke` to `POST /invocations`; `app.run()`
serves it locally.
"""

from __future__ import annotations

from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.runtime.models import PingStatus
from strands import Agent, tool
from strands.models.bedrock import BedrockModel

from nhis_okf import chat, config, helpers

app = BedrockAgentCoreApp()
log = app.logger


# --- The two tools the agent can call (aggregate-only; never return rows) -----------------

@tool
def tool_search_okf(query: str) -> str:
    """Retrieve a matching verified concept from the OKF bundle (aggregate figures only).
    Here that's in-process TF-IDF over the markdown bundle — no vector DB, no embeddings;
    swap this body for your domain's retrieval."""
    return chat.search_okf(query)


@tool
def tool_analyze_rows(
    variable: str, universe: str, stat: str = "prevalence", q: float = 0.5
) -> str:
    """Run the live, allow-listed query and return an AGGREGATE answer — never raw records.
    Here that's a survey-weighted pandas/pyarrow query over the parquet bundled in the CodeZip
    (with a design-based CI); swap this body for a SQL query or an API call in your domain."""
    return chat.analyze_rows(variable, universe, stat=stat, q=q)


# --- The grounded agent ------------------------------------------------------------------

def build_grounded_agent() -> Agent:
    """Assemble the agent that answers a question — this object IS the reasoning loop.

    Strands hands the question, the system prompt, and the two tools to Claude on Amazon
    Bedrock. Claude reads the question, decides which tool to call, calls it, reads back only
    what the tool returns, and writes the grounded answer. Three simple pieces:
      * model  — which LLM answers (a Claude model on Bedrock),
      * prompt — the rules it must follow (grounded-or-refuse; see chat.OKF_ANALYST_PROMPT),
      * tools  — the only things it is allowed to call (both aggregate-only).
    Built fresh per request (so each answer is stateless, and `import main` needs no AWS creds).
    """
    return Agent(
        model=BedrockModel(
            model_id=config.bedrock_model_id(),
            region_name=config.aws_region(),
            max_tokens=helpers.MAX_OUTPUT_TOKENS,
        ),
        system_prompt=chat.OKF_ANALYST_PROMPT,
        tools=[tool_search_okf, tool_analyze_rows],
    )


def _parse_question(payload: dict[str, Any]) -> str | None:
    for key in ("question", "query", "prompt"):
        value = (payload or {}).get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


@app.entrypoint
def invoke(payload: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Answer one question grounded in the verified OKF bundle."""
    question = _parse_question(payload)
    if question is None:
        return {"error": "no question provided", "answered": False}
    if len(question) > helpers.MAX_QUESTION_CHARS:
        return {
            "answered": False,
            "mode": "rejected",
            "answer": (
                f"Question too long (limit {helpers.MAX_QUESTION_CHARS} characters). "
                f"Please ask a shorter, specific question.\n\n{helpers.SAFETY}"
            ),
            "citations": [],
        }

    log.info("OKF query: %s", question)
    # Retrieve grounding once: it seeds the agent's citations and is the fallback answer's
    # source if the Bedrock agent is unavailable.
    hits = helpers.retrieve(question)
    try:
        # Run the agent: Claude reads the question and calls the two tools above to answer it.
        agent = build_grounded_agent()
        text = str(agent(question)).strip()
        answer_text = f"{text}\n\n{helpers.SAFETY}"
        mode = "generative"
        citations = [helpers._citation(h) for h in hits]
    except Exception as exc:  # never fail the query — fall back to a grounded extractive answer
        ans = helpers.extractive_answer(question, hits)
        answer_text = f"[generative unavailable: {exc}; using extractive]\n\n{ans.text}"
        mode = ans.mode
        citations = ans.citations

    return {
        "answered": True,
        "mode": mode,
        "answer": answer_text,
        "citations": citations,
    }


@app.ping
def ping() -> PingStatus:
    return PingStatus.HEALTHY


__all__ = ["app"]

if __name__ == "__main__":
    app.run()
