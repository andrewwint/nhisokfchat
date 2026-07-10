"""AgentCore runtime entrypoint (thin shim).

This does NOT implement an agent — it re-exports the single reviewed agent from the
`nhis_okf` package that ships beside it. The agent answers ONLY from the verified OKF bundle
(`nhis_okf/okf_bundle/`), cites the concept id, and refuses when the bundle has no answer.

Before importing the agent it:
  * NHIS_RUNTIME_TOOLS=retrieval  -> register only the verified-bundle retrieval tool
    (no pandas in the CodeZip), and
  * NHIS_OKF_DIR -> the verified bundle shipped beside the code.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("NHIS_RUNTIME_TOOLS", "retrieval")
os.environ.setdefault(
    "NHIS_OKF_DIR", str(Path(__file__).resolve().parent / "nhis_okf" / "okf_bundle")
)

from nhis_okf.agentcore_app import app  # noqa: E402  (env must be set before import)

__all__ = ["app"]

if __name__ == "__main__":
    app.run()
