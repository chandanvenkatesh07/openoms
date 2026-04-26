"""Policy loading helpers for deterministic sourcing configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_POLICY_PATH = Path(__file__).resolve().parent.parent / "policies" / "default.yaml"


def load_policy(policy_path: str | Path | None = None) -> dict[str, Any]:
    resolved = Path(policy_path) if policy_path is not None else DEFAULT_POLICY_PATH
    with resolved.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded
