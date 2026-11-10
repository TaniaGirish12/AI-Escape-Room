"""Version 2 - a thin wrapper around the Gemini API.

Keeping the API call in one place means the rest of the game only needs a
`generate(system, prompt)` function, and the tests can swap in a fake LLM.
"""

import os
import time

from google import genai
from google.genai import types

DEFAULT_MODEL = "gemini-3.8-flash"


class LLMError(Exception):
    """The LLM could not be used (no key, network problem, rate limit, empty answer)."""


class GeminiLLM:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        api_key = api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self.available = bool(api_key) and api_key != "your_api_key_here"
        self.client = genai.Client(api_key=api_key) if self.available else None
        self.last_error = ""

    def generate(self, system: str, prompt: str, json_schema: dict | None = None) -> str:
        """Return the model's text answer. With json_schema the answer is JSON text."""
        if not self.available:
            raise LLMError("GEMINI_API_KEY is not set.")

        settings = {"system_instruction": system}
        if json_schema:
            settings["response_mime_type"] = "application/json"
            settings["response_json_schema"] = json_schema
        config = types.GenerateContentConfig(**settings)

        for attempt in (1, 2):                  # one retry for short hiccups (rate limit, overload)
            try:
                response = self.client.models.generate_content(
                    model=self.model, contents=prompt, config=config)
                text = (response.text or "").strip()
                if text:
                    self.last_error = ""
                    return text
                self.last_error = "empty answer"
            except Exception as error:
                self.last_error = str(error)
            if attempt == 1:
                time.sleep(2)
        raise LLMError(self.last_error)
