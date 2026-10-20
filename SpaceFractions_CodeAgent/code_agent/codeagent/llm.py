"""Minimal DeepSeek chat-completions client (OpenAI-compatible, tool calling)."""
from __future__ import annotations

import time
from typing import Any

import requests

BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-pro"


class LLMError(RuntimeError):
    pass


class DeepSeekClient:
    def __init__(self, api_key: str, model: str = MODEL, base_url: str = BASE_URL,
                 timeout: int = 300, max_retries: int = 3, thinking: bool = False):
        if not api_key or not api_key.strip():
            raise LLMError("DeepSeek API key is empty.")
        self.api_key = api_key.strip()
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.thinking = thinking

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
             max_tokens: int = 16384) -> dict[str, Any]:
        """Send one chat request and return the assistant message dict."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "thinking": {"type": "enabled" if self.thinking else "disabled"},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                r = requests.post(f"{self.base_url}/chat/completions", json=payload,
                                  headers=headers, timeout=self.timeout)
            except requests.RequestException as e:  # network error: retry
                last = e
            else:
                if r.status_code == 200:
                    choice = r.json()["choices"][0]
                    msg = choice["message"]
                    msg["_finish_reason"] = choice.get("finish_reason")
                    return msg
                if r.status_code in (401, 402, 403):
                    raise LLMError(f"Authentication/billing error {r.status_code}: {r.text[:300]}")
                if r.status_code == 400:
                    raise LLMError(f"Bad request: {r.text[:500]}")
                last = LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
            time.sleep(2 ** attempt)
        raise LLMError(f"DeepSeek request failed after {self.max_retries} attempts: {last}")
