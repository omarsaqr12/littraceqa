"""A `GeminiClient`-shaped client backed by a local OpenAI-compatible server.

Written to remove the API budget from the stage that needs it most. Paper
selection is the binding constraint on the score -- paper F1 is 1/3 of the total
and evidence recall is capped by `paper_recall x locator_accuracy` -- and the
hosted path cannot support experimenting on it: `gemini-3.7-flash` exhausts its
free per-day quota in roughly fifteen calls, which is not enough to score one
validation split, let alone compare two configurations.

Selection is also the stage best suited to a local model. It reads 30 titles and
abstracts, about 5k tokens, and picks indices -- recognition over a list, not the
long-document reading where the local reader previously lost to the hosted one
(reports/local_reader.md). Nothing here needs vision or a 1M context.

Implements only the surface `LLMPaperSelector` uses, so it can be swapped in
without touching the caller.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .client import RateLimiter, Usage, parse_json

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "cache" / "local_llm"


class LocalChatClient:
    """Chat-completions client with the same call surface as `GeminiClient`."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        *,
        api_key: str | None = None,
        model: str = "local",
        timeout: float = 300.0,
        temperature: float = 0.0,
        max_retries: int = 3,
        rpm: int = 0,
        cache_dir: Path = CACHE_DIR,
    ):
        self.base_url = base_url.rstrip("/")
        #: Set for hosted OpenAI-compatible providers (Groq, Cerebras); the
        #: local llama-server needs no auth.
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_retries = max_retries
        self.limiter = RateLimiter(rpm)
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.usage = Usage()
        self._session = None

    @property
    def available(self) -> bool:
        try:
            import requests

            return self.session.get(f"{self.base_url}/v1/models", timeout=15).ok
        except Exception:
            return False

    @property
    def session(self):
        if self._session is None:
            import requests

            self._session = requests.Session()
            if self.api_key:
                self._session.headers["Authorization"] = f"Bearer {self.api_key}"
        return self._session

    def _cache_path(self, prompt: str, schema: Any, model: str) -> Path:
        digest = hashlib.sha256()
        digest.update(model.encode())
        digest.update(b"\x00")
        digest.update(prompt.encode())
        if schema is not None:
            digest.update(json.dumps(schema, sort_keys=True, default=str).encode())
        return self.cache_dir / f"{digest.hexdigest()[:32]}.json"

    def generate(
        self,
        prompt: str,
        *,
        attachments: list | None = None,
        schema: Any = None,
        model: str | None = None,
        max_output_tokens: int = 2048,
        use_cache: bool = True,
        extra_config: dict[str, Any] | None = None,
        thinking_budget: int | None = None,
    ) -> str:
        if attachments:
            # This backend is text-only by design; the caller should not be
            # sending PDFs or images here.
            raise ValueError("LocalChatClient does not accept attachments")

        model = model or self.model
        path = self._cache_path(prompt, schema, model)
        if use_cache and path.exists():
            self.usage.cache_hits += 1
            return json.loads(path.read_text(encoding="utf-8"))["text"]

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_output_tokens,
            "temperature": self.temperature,
        }
        if self.api_key is None:
            # llama.cpp extension: Qwen3 thinks by default under --jinja and
            # would spend the token budget before emitting JSON. Hosted
            # providers reject unknown request fields, so only send it locally.
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": schema},
            }

        last: Exception | None = None
        for attempt in range(self.max_retries):
            self.limiter.acquire()
            try:
                response = self.session.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload, timeout=self.timeout,
                )
                response.raise_for_status()
                text = (response.json().get("choices") or [{}])[0] \
                    .get("message", {}).get("content", "") or ""
            except Exception as exc:  # noqa: BLE001
                last, _ = exc, self.usage.__setattr__("errors", self.usage.errors + 1)
                time.sleep(min(2**attempt, 20))
                continue
            self.usage.record(model)
            if text.strip():
                if use_cache:
                    path.write_text(
                        json.dumps({"text": text, "model": model}, ensure_ascii=False),
                        encoding="utf-8",
                    )
                return text
            self.usage.errors += 1
            payload["max_tokens"] = min(int(payload["max_tokens"]) * 2, 16384)
        raise RuntimeError(f"local model failed after {self.max_retries} attempts: {last}")

    def generate_json(
        self, prompt: str, *, schema: Any = None, default: Any = None, **kwargs
    ) -> Any:
        try:
            return parse_json(self.generate(prompt, schema=schema, **kwargs), default)
        except Exception:
            return default
