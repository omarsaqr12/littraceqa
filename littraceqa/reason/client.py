"""Provider-agnostic LLM client with a disk cache, rate limiting, and retries.

Built around a free-tier budget that is far tighter than the published guidance
suggests: quota is enforced **per model per day**, and `gemini-flash-latest`
(= gemini-3.6-flash) allows only **20 requests/day**. A 71-question test run
needs ~210 calls. Four properties follow, and they matter more than throughput:

* **Every response is cached on disk**, keyed by a hash of model + prompt +
  attachment bytes. Re-running the pipeline after a downstream bug costs nothing,
  and an ablation that changes only stage E does not re-read a single PDF.
* **Models rotate on quota exhaustion.** Since the limit is per model, a chain of
  three models is three budgets.
* **A per-day 429 is never retried** -- it is terminal for that model, and on a
  20/day budget blind retries spend the entire allowance on failures. Only
  per-minute 429s are retried, honouring the server's `retryDelay`.
* **Rate limiting is enforced client-side**, because free tiers answer a burst
  with 429s that eat the quota anyway.
* **PDFs are sent natively** rather than as rendered page images. Gemini accepts
  application/pdf directly and its 1M context swallows a whole paper, so one call
  can return the answer *and* its page number -- the alternative (shortlist pages,
  render, send images) costs several calls per paper and introduces a
  page-selection failure mode before the model ever sees the right page.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "cache" / "llm"


@dataclass(slots=True)
class Attachment:
    data: bytes
    mime_type: str = "application/pdf"
    #: Stable identity for cache keying, so we hash a short id, not 5MB.
    key: str = ""

    def cache_key(self) -> str:
        return self.key or hashlib.sha1(self.data).hexdigest()[:20]


@dataclass
class Usage:
    calls: int = 0
    cache_hits: int = 0
    errors: int = 0
    by_model: dict[str, int] = field(default_factory=dict)

    def record(self, model: str) -> None:
        self.calls += 1
        self.by_model[model] = self.by_model.get(model, 0) + 1

    def __str__(self) -> str:
        return (f"calls={self.calls} cache_hits={self.cache_hits} errors={self.errors} "
                f"by_model={self.by_model}")


class RateLimiter:
    """Simple sliding-window limiter: at most `rpm` starts per 60s."""

    def __init__(self, rpm: int):
        self.rpm = rpm
        self._starts: list[float] = []

    def acquire(self) -> None:
        if self.rpm <= 0:
            return
        now = time.time()
        self._starts = [t for t in self._starts if now - t < 60.0]
        if len(self._starts) >= self.rpm:
            time.sleep(max(0.0, 60.0 - (now - self._starts[0])) + 0.05)
            self._starts = [t for t in self._starts if time.time() - t < 60.0]
        self._starts.append(time.time())


#: Free-tier quota is **per model per day**, and it is small: `gemini-flash-latest`
#: resolves to gemini-3.6-flash with a measured limit of **20 requests/day**
#: (quotaId `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, quotaValue 20).
#: A 71-question test run needs ~210 calls, so no single model can carry a run.
#: Rotating across models multiplies the daily budget; the order puts the
#: cheapest-per-quota first and keeps the strongest in reserve for what is left.
DEFAULT_MODEL_CHAIN = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash",
    "gemini-flash-latest",
]


class QuotaExhausted(RuntimeError):
    """Every model in the chain has hit its per-day free-tier limit."""


class GeminiClient:
    """Google AI Studio client. Free tier: multimodal, native PDF, 1M context."""

    def __init__(
        self,
        model: str | list[str] = None,
        *,
        api_key: str | None = None,
        rpm: int = 8,
        max_retries: int = 5,
        cache_dir: Path = CACHE_DIR,
        temperature: float = 0.0,
        thinking_budget: int | None = 0,
    ):
        chain = model if isinstance(model, list) else ([model] if model else DEFAULT_MODEL_CHAIN)
        self.model_chain = list(dict.fromkeys(chain))
        self.model = self.model_chain[0]
        #: Models observed to have spent their per-day allowance this run.
        self.exhausted: set[str] = set()
        #: Models that reject `thinking_config` outright (flash-lite 400s on it).
        self._no_thinking: set[str] = set()
        self.temperature = temperature
        self.max_retries = max_retries
        # Current Flash models think by default, and thinking tokens are drawn
        # from the same budget as the response: ask for 1400 tokens and you can
        # get an *empty* body back with the whole budget spent reasoning. Every
        # call here has a small, schema-constrained answer, so thinking buys
        # little and costs reliability. None leaves the model's default alone.
        self.thinking_budget = thinking_budget
        self.limiter = RateLimiter(rpm)
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.usage = Usage()
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY") or ""
        self._client = None

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    @property
    def client(self):
        if self._client is None:
            if not self._api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is not set. Copy .env.example to .env and fill it in."
                )
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    # -- cache ---------------------------------------------------------------

    def _cache_path(
        self, prompt: str, attachments: list[Attachment], schema: Any, model: str
    ) -> Path:
        digest = hashlib.sha256()
        digest.update(model.encode())
        digest.update(b"\x00")
        digest.update(prompt.encode())
        for attachment in attachments:
            digest.update(b"\x00")
            digest.update(attachment.cache_key().encode())
        if schema is not None:
            digest.update(json.dumps(schema, sort_keys=True, default=str).encode())
        return self.cache_dir / f"{digest.hexdigest()[:32]}.json"

    # -- generation ----------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        attachments: list[Attachment] | None = None,
        schema: Any = None,
        model: str | None = None,
        max_output_tokens: int = 2048,
        use_cache: bool = True,
    ) -> str:
        """Return raw model text. `schema` requests structured JSON output."""
        attachments = attachments or []
        model = model or self.model
        path = self._cache_path(prompt, attachments, schema, model)
        if use_cache and path.exists():
            self.usage.cache_hits += 1
            return json.loads(path.read_text(encoding="utf-8"))["text"]

        from google.genai import types

        parts: list[Any] = [
            types.Part.from_bytes(data=a.data, mime_type=a.mime_type) for a in attachments
        ]
        parts.append(types.Part.from_text(text=prompt))

        config: dict[str, Any] = {
            "temperature": self.temperature,
            "max_output_tokens": max_output_tokens,
        }
        if schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = schema
        if self.thinking_budget is not None:
            try:
                config["thinking_config"] = types.ThinkingConfig(
                    thinking_budget=self.thinking_budget
                )
            except Exception:
                pass  # older SDK -- `_try_model` also strips it per model

        # Candidate models for this call: the requested one first, then the rest
        # of the chain, skipping any already known to be out of daily quota.
        candidates = [m for m in [model, *self.model_chain] if m not in self.exhausted]
        candidates = list(dict.fromkeys(candidates))
        if not candidates:
            raise QuotaExhausted(
                f"all models exhausted for today: {sorted(self.exhausted)}. "
                "Free-tier quota is per model per day; try again tomorrow or add a model."
            )

        last_error: Exception | None = None
        for active in candidates:
            text, last_error = self._try_model(active, parts, dict(config))
            if text is None:
                continue
            if use_cache:
                path.write_text(
                    json.dumps({"text": text, "model": active}, ensure_ascii=False),
                    encoding="utf-8",
                )
            return text

        raise RuntimeError(f"Gemini call failed on {candidates}: {last_error}")

    def _try_model(
        self, model: str, parts: list[Any], config: dict[str, Any]
    ) -> tuple[str | None, Exception | None]:
        """Attempt one model with retries. Returns (text, error); text=None on failure.

        Marks the model exhausted on a per-day 429 so the caller rotates instead
        of retrying -- on a 20-requests/day model, blind retries spend the entire
        allowance on failures.
        """
        from google.genai import types

        # Not every model accepts `thinking_config`: flash-lite rejects
        # thinking_budget=0 with 400 INVALID_ARGUMENT. Learned once per model.
        if model in self._no_thinking:
            config.pop("thinking_config", None)

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            self.limiter.acquire()
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=[types.Content(role="user", parts=parts)],
                    config=types.GenerateContentConfig(**config),
                )
                text = response.text or ""
            except Exception as exc:  # noqa: BLE001 -- provider raises many shapes
                last_error = exc
                self.usage.errors += 1
                message, lowered = str(exc), str(exc).lower()
                if any(k in lowered for k in ("api key", "permission", "not found")):
                    return None, exc
                if "429" in message or "resource_exhausted" in lowered:
                    if "perday" in lowered.replace("_", "").replace("-", ""):
                        self.exhausted.add(model)
                        return None, exc
                    time.sleep(_retry_delay(message, min(2**attempt + 1.0, 60.0)))
                    continue
                if "invalid_argument" in lowered and "thinking_config" in config:
                    # Almost certainly the thinking config. Drop it and retry
                    # immediately rather than burning the backoff ladder.
                    self._no_thinking.add(model)
                    config.pop("thinking_config", None)
                    continue
                time.sleep(min(2**attempt + random.random(), 45.0))
                continue

            self.usage.record(model)
            if text.strip():
                return text, None
            # Empty body: budget spent on thinking, or a safety stop. Give it
            # more room rather than caching nothing.
            self.usage.errors += 1
            last_error = RuntimeError("empty response body")
            config["max_output_tokens"] = min(int(config["max_output_tokens"]) * 2, 16384)
        return None, last_error

    def generate_json(
        self, prompt: str, *, schema: Any = None, default: Any = None, **kwargs
    ) -> Any:
        """`generate` plus tolerant JSON parsing; returns `default` on failure."""
        try:
            text = self.generate(prompt, schema=schema, **kwargs)
        except Exception:
            return default
        return parse_json(text, default)


_RETRY_DELAY = re.compile(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)s")


def _retry_delay(message: str, default: float) -> float:
    """Honour the server's `retryDelay` on a per-minute 429 when it gives one."""
    match = _RETRY_DELAY.search(message)
    return min(float(match.group(1)) + 1.0, 90.0) if match else default


def parse_json(text: str, default: Any = None) -> Any:
    """Parse JSON that may be wrapped in prose or a ```json fence."""
    text = (text or "").strip()
    if not text:
        return default
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = text.find(opener), text.rfind(closer)
        if 0 <= start < end:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return default
