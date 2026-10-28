"""List the NVIDIA models your Token Factory key can call, and make one tiny JSON test call.

Reads NEBIUS_API_KEY (and optionally NEBIUS_BASE_URL, TERMPLAN_MODEL) from the environment or .env.
Run: .venv/bin/python scripts/check_models.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from termplan.config import get_settings  # noqa: E402
from termplan.llm import ChatClient, LLMError  # noqa: E402
from termplan.textutil import parse_json_payload  # noqa: E402


def main() -> int:
    s = get_settings()
    if not s.key_configured:
        print("NEBIUS_API_KEY is not set (put it in .env).")
        return 1
    client = ChatClient(api_key=s.api_key, base_url=s.base_url, timeout=60)
    models = client.list_models()
    nvidia = [m for m in models if m.lower().startswith("nvidia/")]
    print(f"{len(models)} models at {s.base_url}; NVIDIA ones:")
    for m in nvidia:
        print(f"  {m}{'   <- TERMPLAN_MODEL' if m == s.model else ''}")
    if s.model not in models:
        print(f"\nTERMPLAN_MODEL={s.model} is NOT in the list. Pick a Nemotron ID above and set it in .env.")
        return 2
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}
    try:
        c = client.complete(model=s.model, schema=schema, max_tokens=200, messages=[
            {"role": "user", "content": 'Reply with the JSON object {"ok": true} and nothing else.'}])
    except LLMError as exc:
        print(f"Test call failed: {exc}")
        return 3
    print(f"\nTest call: mode={c.mode} finish={c.finish_reason} latency={c.latency_s:.2f}s "
          f"tokens={c.usage.get('total_tokens')} -> {parse_json_payload(c.text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
