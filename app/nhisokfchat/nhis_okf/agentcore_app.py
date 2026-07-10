"""AgentCore Runtime entrypoint for the NHIS-OKF chat.

Mirrors the `agentcore create` (Strands + Bedrock) template: `app = BedrockAgentCoreApp()`
with an `@app.entrypoint` invocation handler and `app.run()` for the local server. The SDK
provides `GET /ping` (liveness); `@app.ping` reports status; the entrypoint maps to
`POST /invocations`.

The invocation is grounded by construction: it answers only from the verified OKF bundle
via `chat.answer`, which retrieves from `.okf/variables/` and (in generative mode) runs the
Strands agent whose only tool reads that same verified bundle. A quarantined figure cannot
be served. This module imports `bedrock_agentcore`, so it is only loaded at deploy time;
`compile`/`verify`/`query` never import it.
"""

from __future__ import annotations

from typing import Any

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from bedrock_agentcore.runtime.models import PingStatus

from .chat import answer

app = BedrockAgentCoreApp()
log = app.logger


def _parse_question(payload: dict[str, Any]) -> str | None:
    for key in ("question", "query", "prompt"):
        value = (payload or {}).get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


@app.entrypoint
def invoke(payload: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """Answer a question grounded in the verified OKF bundle."""
    question = _parse_question(payload)
    if question is None:
        return {"error": "no question provided", "answered": False}

    log.info("OKF query: %s", question)
    # Force the generative (Bedrock) path at deploy: there's no ANTHROPIC_API_KEY and no
    # injected model here, so answer()'s auto-detect would otherwise fall to extractive
    # (which "refuses" by returning the nearest concept). Generative gives clean
    # grounded-or-refuse; it falls back to extractive automatically if Bedrock errors.
    ans = answer(question, generative=True)  # grounded by construction
    return {
        "answered": True,
        "mode": ans.mode,
        "answer": ans.text,
        "citations": ans.citations,
    }


@app.ping
def ping() -> PingStatus:
    return PingStatus.HEALTHY


if __name__ == "__main__":
    app.run()
