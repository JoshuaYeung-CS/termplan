"""Thin client around the OpenAI-compatible Nebius Token Factory chat completions API."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
from openai import APIConnectionError, APIStatusError, BadRequestError, OpenAI, RateLimitError

log = logging.getLogger("termplan.llm")

# Order in which structured-output modes are tried. Token Factory documents both
# {"type": "json_schema"} and {"type": "json_object"}; support varies by model, so a 400 on one
# mode falls through to the next. The schema is always included in the prompt as well.
_MODES = ("json_schema", "json_object", "none")


@dataclass
class Completion:
    text: str
    finish_reason: Optional[str]
    model: str
    mode: str
    latency_s: float
    usage: dict = field(default_factory=dict)


class LLMError(RuntimeError):
    pass


class ChatClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float = 120.0,
        http_client: Optional[httpx.Client] = None,
        max_retries: int = 3,
    ) -> None:
        self._client = OpenAI(
            api_key=api_key or "missing-key",
            base_url=base_url,
            timeout=timeout,
            max_retries=0,  # retries handled below so 429/5xx backoff is visible in logs
            http_client=http_client,
        )
        self._max_retries = max_retries
        self._mode_index: dict[str, int] = {}
        self.calls: int = 0

    def _response_format(self, mode: str, schema: dict) -> Optional[dict]:
        if mode == "json_schema":
            return {
                "type": "json_schema",
                "json_schema": {"name": "termplan_output", "schema": schema, "strict": False},
            }
        if mode == "json_object":
            return {"type": "json_object"}
        return None

    def complete(
        self,
        *,
        model: str,
        messages: list[dict],
        schema: dict,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> Completion:
        start_mode = self._mode_index.get(model, 0)
        last_error: Optional[Exception] = None
        for mode_i in range(start_mode, len(_MODES)):
            mode = _MODES[mode_i]
            kwargs: dict[str, Any] = dict(
                model=model, messages=messages, max_tokens=max_tokens, temperature=temperature
            )
            rf = self._response_format(mode, schema)
            if rf is not None:
                kwargs["response_format"] = rf
            try:
                result = self._call_with_retries(kwargs, mode)
            except BadRequestError as exc:
                if mode == "none":
                    raise LLMError(f"Token Factory rejected the request: {exc}") from exc
                log.warning("model=%s rejected response_format=%s (%s); trying next mode",
                            model, mode, _short(exc))
                last_error = exc
                continue
            self._mode_index[model] = mode_i
            return result
        raise LLMError(f"No structured-output mode accepted: {last_error}")

    def _call_with_retries(self, kwargs: dict, mode: str) -> Completion:
        delay = 1.0
        for attempt in range(self._max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = self._client.chat.completions.create(**kwargs)
            except (RateLimitError, APIConnectionError) as exc:
                if attempt >= self._max_retries:
                    raise LLMError(f"Token Factory unavailable after retries: {_short(exc)}") from exc
                log.warning("retrying after %s (sleep %.1fs)", type(exc).__name__, delay)
                time.sleep(delay)
                delay *= 2
                continue
            except APIStatusError as exc:
                if exc.status_code >= 500 and attempt < self._max_retries:
                    log.warning("retrying after HTTP %s (sleep %.1fs)", exc.status_code, delay)
                    time.sleep(delay)
                    delay *= 2
                    continue
                if isinstance(exc, BadRequestError):
                    raise
                raise LLMError(f"Token Factory error HTTP {exc.status_code}: {_short(exc)}") from exc
            latency = time.perf_counter() - t0
            self.calls += 1
            choice = resp.choices[0]
            text = choice.message.content or ""
            usage = resp.usage.model_dump() if getattr(resp, "usage", None) else {}
            log.info(
                "nemotron call model=%s mode=%s finish=%s latency=%.2fs tokens=%s",
                kwargs["model"], mode, choice.finish_reason, latency,
                usage.get("total_tokens", "?"),
            )
            return Completion(
                text=text, finish_reason=choice.finish_reason, model=kwargs["model"],
                mode=mode, latency_s=latency, usage=usage,
            )
        raise LLMError("unreachable")

    def list_models(self) -> list[str]:
        return sorted(m.id for m in self._client.models.list())


def _short(exc: Exception) -> str:
    msg = str(exc)
    return msg if len(msg) < 240 else msg[:240] + "..."
