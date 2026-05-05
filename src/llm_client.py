"""Thin OpenAI chat-completions wrapper with a hard token budget.

The agent layer talks to this class only; tests inject a fake client with the
same `chat(system, user) -> str` shape. See specs/llm_agent.md.
"""

from __future__ import annotations

import os
import sys
from typing import Optional


_DEFAULT_MODEL = "gpt-5-mini"
_DEFAULT_BUDGET = 50_000
_CHARS_PER_TOKEN_ESTIMATE = 4  # conservative fallback if tiktoken unavailable


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)


class LLMClient:
    """OpenAI chat wrapper. Tracks token usage and stops calling once the
    budget is exhausted (the agent then falls back to its random brain).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
        token_budget: int = _DEFAULT_BUDGET,
    ):
        # Lazy import so tests don't require the openai SDK.
        from openai import OpenAI

        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY not set. Add it to .env or export it in the shell."
            )
        self._client = OpenAI(api_key=key)
        self.model = model
        self.token_budget = token_budget
        self.tokens_used = 0

    @property
    def is_exhausted(self) -> bool:
        return self.tokens_used >= self.token_budget

    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        if self.is_exhausted:
            raise RuntimeError("LLM token budget exhausted")
        # Note: we deliberately don't pass `temperature` — newer OpenAI models
        # (gpt-5 family, o-series) reject any value other than the default.
        request: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            request["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(**request)
        usage = getattr(response, "usage", None)
        if usage is not None and getattr(usage, "total_tokens", None) is not None:
            self.tokens_used += usage.total_tokens
        else:
            # Fallback estimate if usage is unavailable.
            self.tokens_used += _estimate_tokens(system) + _estimate_tokens(user)
        if self.is_exhausted:
            print(
                f"[llm] token budget {self.token_budget} reached "
                f"({self.tokens_used} used) — agents will fall back to random",
                file=sys.stderr,
            )
        return response.choices[0].message.content or ""


def load_dotenv_if_present() -> None:
    """Best-effort .env loader. Silent no-op if python-dotenv isn't installed."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()
