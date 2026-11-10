"""Version 2 - a thin wrapper around the Gemini API.

Keeping the API call in one place means the rest of the game only needs a
`generate(system, prompt)` function, and the tests can swap in a fake LLM.

The free tier has small per-model limits (for example 5 requests per minute
and 20 per day). Each model has its own quota, so when one model is busy or
out of quota the wrapper moves on to the next model in the list. If every
model fails, LLMError is raised and the game falls back to plain text.
"""

import os
import re
import time

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_FALLBACKS = "gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite"
TIMEOUT_MS = 30_000          # a hanging model must not freeze the game


class LLMError(Exception):
    """The LLM could not be used (no key, network problem, rate limit, empty answer)."""


def _cooldown_seconds(error_text: str) -> float:
    """How long to leave a model alone after an error."""
    if "RESOURCE_EXHAUSTED" in error_text or "429" in error_text:
        if "per day" in error_text.lower() or "PerDay" in error_text:
            return 6 * 3600                       # daily quota used up
        match = re.search(r"retry in ([\d.]+)s", error_text)
        return float(match.group(1)) + 1 if match else 60
    if any(code in error_text for code in ("UNAVAILABLE", "503", "DEADLINE_EXCEEDED", "504", "timed out")):
        return 60                                 # model overloaded or too slow
    if "NOT_FOUND" in error_text or "404" in error_text:
        return 24 * 3600                          # model retired
    return 0                                      # other errors: do not block the model


class GeminiLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 fallbacks: list[str] | None = None):
        api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        if fallbacks is None:
            fallbacks = os.getenv("GEMINI_FALLBACK_MODELS", DEFAULT_FALLBACKS).split(",")
        self.models = [self.model] + [m.strip() for m in fallbacks if m.strip() and m.strip() != self.model]
        self.available = bool(api_key) and api_key != "your_api_key_here"
        self.client = (genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_MS))
                       if self.available else None)
        self.blocked_until: dict[str, float] = {}
        self.last_error = ""
        self.last_model = ""

    def generate(self, system: str, prompt: str, json_schema: dict | None = None) -> str:
        """Return the model's text answer. With json_schema the answer is JSON text."""
        if not self.available:
            raise LLMError("GEMINI_API_KEY is not set.")

        settings = {"system_instruction": system}
        if json_schema:
            settings["response_mime_type"] = "application/json"
            settings["response_json_schema"] = json_schema
        config = types.GenerateContentConfig(**settings)

        errors = []
        for model in self.models:
            if self.blocked_until.get(model, 0) > time.time():
                continue
            try:
                response = self.client.models.generate_content(model=model, contents=prompt, config=config)
                text = (response.text or "").strip()
                if text:
                    self.last_error, self.last_model = "", model
                    return text
                errors.append(f"{model}: empty answer")
            except Exception as error:
                message = str(error)
                errors.append(f"{model}: {message[:120]}")
                cooldown = _cooldown_seconds(message)
                if cooldown:
                    self.blocked_until[model] = time.time() + cooldown
        self.last_error = " | ".join(errors) or "all models are cooling down after rate limits"
        raise LLMError(self.last_error)
