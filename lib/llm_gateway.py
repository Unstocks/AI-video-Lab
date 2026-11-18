"""Optional headless OpenAI-compatible LLM gateway for evals & CLI automation (BU-5.3).

Targets ``AI_VIDEO_LAB_LLM_BASE_URL`` (default ``http://127.0.0.1:8082/v1`` —
Free Claude Code's OpenAI-compatible endpoint) using the repo's existing
``openai`` + ``pydantic`` packages with progressive structured-output fallback:

  1. ``response_format={"type": "json_schema", ...}`` (strict JSON Schema)
  2. ``response_format={"type": "json_object"}`` (JSON mode)
  3. Plain text completion with fenced/balanced JSON extraction
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional, Type, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

DEFAULT_BASE_URL = "http://127.0.0.1:8082/v1"
DEFAULT_API_KEY = "free-claude-code"
DEFAULT_MODEL = "claude-sonnet-4-6"

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def extract_json_payload(raw_text: str) -> Any:
    """Extract a JSON object/array from plain or markdown-fenced LLM output."""
    cleaned = (raw_text or "").strip()
    if not cleaned:
        raise ValueError("LLM returned empty response.")

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    fence = _FENCE_RE.search(cleaned)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Balanced brace/bracket scan fallback
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = cleaned.find(open_ch)
        if start == -1:
            continue
        end = cleaned.rfind(close_ch)
        if end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                continue

    raise ValueError(f"Could not extract valid JSON from LLM response: {cleaned[:200]!r}")


class LLMGateway:
    """Thin OpenAI-compatible structured-output client for headless automation."""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 120.0,
        client: Any = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("AI_VIDEO_LAB_LLM_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.api_key = api_key or os.environ.get("AI_VIDEO_LAB_LLM_API_KEY") or DEFAULT_API_KEY
        self.model = model or os.environ.get("AI_VIDEO_LAB_LLM_MODEL") or DEFAULT_MODEL
        self.timeout = float(timeout)
        self._client = client

    def _get_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                timeout=self.timeout,
            )
        return self._client

    def complete_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_model: Type[T],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> T:
        """Request a Pydantic-validated response using progressive schema fallback."""
        client = self._get_client()
        schema = response_model.model_json_schema()
        base_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        strategies: list[dict[str, Any]] = [
            {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "schema": schema,
                        "strict": True,
                    },
                }
            },
            {"response_format": {"type": "json_object"}},
            {},
        ]

        last_error: Optional[Exception] = None
        for idx, extra in enumerate(strategies):
            messages = list(base_messages)
            if idx == 2:
                messages = [
                    {
                        "role": "system",
                        "content": (
                            f"{system_prompt}\n\n"
                            f"Respond ONLY with valid JSON conforming to:\n{json.dumps(schema)}"
                        ),
                    },
                    {"role": "user", "content": user_prompt},
                ]
            try:
                resp = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **extra,
                )
                content = (resp.choices[0].message.content or "") if resp.choices else ""
                parsed = extract_json_payload(content)
                return response_model.model_validate(parsed)
            except Exception as exc:
                last_error = exc
                continue

        raise RuntimeError(f"LLMGateway structured completion failed after all fallbacks: {last_error}") from last_error
