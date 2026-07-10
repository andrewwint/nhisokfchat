"""Runtime configuration for the chat agent (model + region selection).

Local testing uses the Anthropic API (ANTHROPIC_API_KEY). The deploy target is Strands on
Bedrock AgentCore, which uses AWS credentials and a Bedrock model id. Both are overridable
by environment variables so nothing is hard-pinned.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repo root: src/nhis_okf/config.py -> parents[2].
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _shipped_bundle_dir() -> Path:
    """The bundle location shipped alongside the vendored `nhis_okf` package.

    `app/build_runtime.py` vendors `src/nhis_okf/` and copies `.okf/` into
    `<package>/okf_bundle/` at package time, so the CodeZip runtime carries the verified
    bundle beside the code. Used as the final fallback when neither `NHIS_OKF_DIR` nor a
    repo-relative `.okf/` is present (i.e. in the deployed runtime).
    """
    return Path(__file__).resolve().parent / "okf_bundle"


def okf_dir() -> Path:
    """The verified OKF bundle directory.

    Resolution order:
      1. `NHIS_OKF_DIR` env override (the packaged runtime points here explicitly), then
      2. the repo-relative `.okf/` when it exists (local runs and tests, unchanged), then
      3. the bundle shipped inside the installed package (the deployed CodeZip, which has no
         repo-relative `.okf/`).
    """
    override = os.environ.get("NHIS_OKF_DIR")
    if override:
        return Path(override)
    repo_bundle = _REPO_ROOT / ".okf"
    if repo_bundle.exists():
        return repo_bundle
    return _shipped_bundle_dir()


def aws_region() -> str:
    return os.environ.get("BEDROCK_REGION") or os.environ.get("AWS_REGION") or "us-east-1"


def anthropic_model_id() -> str:
    """Model id for the Anthropic API path (local testing)."""
    return os.environ.get("NHIS_ANTHROPIC_MODEL", "claude-sonnet-4-6")


def bedrock_model_id() -> str:
    """Model id for the Bedrock path (AgentCore deploy).

    Confirm the exact Bedrock model id available in your account/region before deploy;
    override with NHIS_BEDROCK_MODEL. Default is a recent Claude Sonnet inference profile.
    """
    return os.environ.get("NHIS_BEDROCK_MODEL", "us.anthropic.claude-sonnet-4-6")


def has_anthropic_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
