"""Groq chat client: schema-constrained JSON output, retries with backoff, usage accounting."""

from __future__ import annotations

import copy
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass
from typing import Optional, Type, TypeVar

import groq
from pydantic import BaseModel, ValidationError

from .settings import Settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_TRANSIENT = (groq.RateLimitError, groq.APITimeoutError, groq.APIConnectionError, groq.InternalServerError)
_DROP_KEYS = ("default", "title", "minimum", "maximum")


class LLMError(RuntimeError):
    """Extraction failed after all retries."""


class QuotaExhausted(LLMError):
    """A daily quota is used up. Retrying within the run cannot help, so the run should stop."""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    requests: int = 0
    retries: int = 0

    def __iadd__(self, other: "Usage") -> "Usage":
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.requests += other.requests
        self.retries += other.retries
        return self


def strict_schema(model: Type[BaseModel]) -> dict:
    """Pydantic JSON schema adapted to strict structured output: closed objects, all keys required."""
    schema = copy.deepcopy(model.model_json_schema())

    def visit(node):
        if isinstance(node, dict):
            for key in _DROP_KEYS:
                if not isinstance(node.get(key), dict):  # never drop a property that happens to share the name
                    node.pop(key, None)
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"])
                node["additionalProperties"] = False
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    return schema


def parse_json_object(text: str) -> dict:
    """Parse a JSON object, tolerating code fences or stray prose around it."""
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise ValueError("no JSON object in model output")
    return json.loads(match.group(0))


class GroqJSONClient:
    def __init__(self, settings: Settings, api_key: Optional[str] = None):
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise LLMError("GROQ_API_KEY is not set (export it or put it in .env)")
        self.settings = settings
        self._client = groq.Groq(api_key=key, timeout=settings.request_timeout_s, max_retries=0)

    def _request(self, messages: list[dict], schema: Type[BaseModel], name: str) -> dict:
        s = self.settings
        req = dict(
            model=s.model,
            messages=messages,
            temperature=s.temperature,
            top_p=s.top_p,
            seed=s.seed,
            max_completion_tokens=s.max_completion_tokens,
        )
        if s.reasoning_effort:
            req["reasoning_effort"] = s.reasoning_effort
            req["include_reasoning"] = False
        if s.structured_output == "strict":
            req["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": name, "schema": strict_schema(schema), "strict": True},
            }
        else:
            req["response_format"] = {"type": "json_object"}
        return req

    def _backoff(self, attempt: int, exc: Exception) -> None:
        s = self.settings
        delay = min(s.backoff_cap_s, s.backoff_base_s * 2 ** (attempt - 1)) * random.uniform(0.5, 1.0)
        retry_after = getattr(getattr(exc, "response", None), "headers", {}).get("retry-after")
        if retry_after:
            try:
                # Honour the server hint, but never park a worker longer than the cap.
                delay = min(max(delay, float(retry_after)), s.backoff_cap_s)
            except ValueError:
                pass
        log.warning("%s (attempt %d, retry-after=%s); sleeping %.1fs: %s",
                    type(exc).__name__, attempt, retry_after, delay, str(exc)[:200])
        time.sleep(delay)

    def complete(self, system: str, user: str, schema: Type[T], name: str) -> tuple[T, Usage]:
        usage = Usage()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        repaired = False

        for attempt in range(1, self.settings.max_attempts + 1):
            try:
                resp = self._client.chat.completions.create(**self._request(messages, schema, name))
            except _TRANSIENT as exc:
                if isinstance(exc, groq.RateLimitError) and "per day" in str(exc):
                    raise QuotaExhausted(str(exc)[:300]) from exc
                usage.retries += 1
                self._backoff(attempt, exc)
                continue
            except groq.BadRequestError as exc:
                # Groq reports schema-decoding failures as 400 json_validate_failed; retry those once.
                if repaired or "json_validate_failed" not in str(exc):
                    raise LLMError(f"bad request: {exc}") from exc
                repaired = True
                usage.retries += 1
                continue

            usage.requests += 1
            if resp.usage:
                usage.prompt_tokens += resp.usage.prompt_tokens or 0
                usage.completion_tokens += resp.usage.completion_tokens or 0
            content = resp.choices[0].message.content or ""
            try:
                return schema.model_validate(parse_json_object(content)), usage
            except (ValueError, ValidationError) as exc:
                if repaired:
                    raise LLMError(f"invalid {name} output after repair: {exc}") from exc
                repaired = True
                usage.retries += 1
                messages = messages + [
                    {"role": "assistant", "content": content[:4000]},
                    {"role": "user", "content": f"That output was invalid ({exc}). Return only the corrected JSON object."},
                ]

        raise LLMError(f"{name}: exhausted {self.settings.max_attempts} attempts")
