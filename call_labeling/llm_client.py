"""Chat client for Cerebras and Groq: schema-constrained JSON, retries, usage accounting.

Both hosts serve the open-weight Qwen 3.8 27B through an OpenAI-compatible
chat API. The openai package is only the HTTP client.
"""

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

import openai
from pydantic import BaseModel, ValidationError

from .settings import Settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

_TRANSIENT = (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError)
_DROP_KEYS = ("default", "title", "minimum", "maximum")


class LLMError(RuntimeError):
    """Extraction failed after all retries."""


class QuotaExhausted(LLMError):
    """The account quota is used up. Retrying within the run cannot help, so the run should stop."""


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


def _quota_exhausted(exc: Exception) -> bool:
    body = getattr(exc, "body", None)
    code = ""
    if isinstance(body, dict):
        err = body.get("error") or {}
        if isinstance(err, dict):
            code = str(err.get("code") or "")
    text = f"{code} {exc}".lower()
    # A spent balance says insufficient_quota. A daily token cap says "per day".
    return "insufficient_quota" in text or "exceeded your current quota" in text or "per day" in text


class JSONClient:
    def __init__(self, settings: Settings, api_key: Optional[str] = None):
        key = api_key or os.environ.get(settings.api_key_env)
        if not key:
            raise LLMError(f"{settings.api_key_env} is not set (export it or put it in .env)")
        self.settings = settings
        kwargs = dict(api_key=key, timeout=settings.request_timeout_s, max_retries=0)
        if settings.base_url:
            kwargs["base_url"] = settings.base_url
        self._client = openai.OpenAI(**kwargs)

    def _request(self, messages: list[dict], schema: Type[BaseModel], name: str) -> dict:
        s = self.settings
        req = dict(
            model=s.model,
            messages=messages,
            max_completion_tokens=s.max_completion_tokens,
        )
        if s.temperature is not None:
            req["temperature"] = s.temperature
        if s.top_p is not None:
            req["top_p"] = s.top_p
        if s.seed is not None:
            req["seed"] = s.seed
        if s.reasoning_effort:
            req["reasoning_effort"] = s.reasoning_effort
        extra = {}
        if s.include_reasoning is not None:
            extra["include_reasoning"] = s.include_reasoning
        if s.reasoning_format:
            extra["reasoning_format"] = s.reasoning_format
        if extra:
            req["extra_body"] = extra
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
        response = getattr(exc, "response", None)
        retry_after = response.headers.get("retry-after") if response is not None else None
        if retry_after:
            try:
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
                if _quota_exhausted(exc):
                    raise QuotaExhausted(str(exc)[:300]) from exc
                usage.retries += 1
                self._backoff(attempt, exc)
                continue
            except openai.BadRequestError as exc:
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
