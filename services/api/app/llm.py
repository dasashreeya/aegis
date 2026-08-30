"""Gemini access for the rules track.

The client is imported lazily so the package installs and the test suite runs without the
`llm` optional dependency. Nothing here is exercised in CI — `tests/test_rules.py` injects a
stub through the `LLMClient` protocol.
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

DEFAULT_MODEL = "gemini-2.5-flash"


class LLMError(RuntimeError):
    """Raised when the model is unreachable or returns something that is not usable JSON."""


class LLMClient(Protocol):
    """The only surface the rule extractor depends on."""

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        ...


class GeminiClient:
    """Structured-output wrapper over google-genai.

    Requires `pip install "./services/api[llm]"` and a key in `GEMINI_API_KEY` or
    `GOOGLE_API_KEY`. The model id can be overridden with `AEGIS_GEMINI_MODEL`.
    """

    def __init__(self, *, api_key: str | None = None, model: str | None = None) -> None:
        try:
            from google import genai
        except ImportError as error:  # pragma: no cover - depends on the optional group
            raise LLMError("Install the 'llm' dependency group to use Gemini") from error

        self._types = __import__("google.genai.types", fromlist=["types"])
        self._model = model or os.environ.get("AEGIS_GEMINI_MODEL", DEFAULT_MODEL)
        key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key:
            raise LLMError("Set GEMINI_API_KEY (or GOOGLE_API_KEY) to use Gemini")
        self._client = genai.Client(api_key=key)

    def generate_json(self, *, system: str, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        from google.genai import errors as genai_errors

        config = self._types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            response_mime_type="application/json",
            response_json_schema=schema,
        )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=config,
            )
        except genai_errors.APIError as error:
            raise LLMError(f"Gemini request failed: {error}") from error

        text = response.text
        if not text:
            raise LLMError("Gemini returned an empty response")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise LLMError("Gemini returned a response that is not valid JSON") from error
        if not isinstance(payload, dict):
            raise LLMError("Gemini returned JSON that is not an object")
        return payload
