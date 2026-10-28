"""Runtime configuration, read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

# Base URL from the Nebius Token Factory quickstart:
# https://docs.tokenfactory.nebius.com/quickstart
DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1/"

# Model ID from the Token Factory docs. "Model Deprecations: November 2026"
# (https://docs.tokenfactory.nebius.com/model-deprecations-november-2026) lists
# nvidia/Nemotron-3_5-Lightning as the replacement for nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B,
# which leaves Serverless on November 9, 2026. Run scripts/check_models.py with your key to
# confirm what your account can call, and override with TERMPLAN_MODEL.
DEFAULT_MODEL = "nvidia/Nemotron-3_5-Lightning"


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines). Existing environment variables win."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model: str
    coach_model: str
    stub: bool
    max_attempts: int
    request_timeout: float

    @property
    def key_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def base_url_host(self) -> str:
        return urlparse(self.base_url).netloc or self.base_url

    @property
    def mode(self) -> str:
        if self.stub:
            return "stub"
        return "nebius" if self.key_configured else "unconfigured"


def get_settings() -> Settings:
    _load_dotenv(Path(os.environ.get("TERMPLAN_ENV_FILE", ".env")))
    model = os.environ.get("TERMPLAN_MODEL", "").strip() or DEFAULT_MODEL
    return Settings(
        api_key=os.environ.get("NEBIUS_API_KEY", "").strip(),
        base_url=os.environ.get("NEBIUS_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        model=model,
        coach_model=os.environ.get("TERMPLAN_COACH_MODEL", "").strip() or model,
        stub=os.environ.get("TERMPLAN_STUB", "").strip().lower() in {"1", "true", "yes"},
        max_attempts=max(1, int(os.environ.get("TERMPLAN_MAX_ATTEMPTS", "3"))),
        request_timeout=float(os.environ.get("TERMPLAN_TIMEOUT", "120")),
    )
