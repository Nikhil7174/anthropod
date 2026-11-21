"""Pinned generation and runtime settings. Recorded verbatim in every run's meta file.

The model is the open-weight gpt-oss-120b. Cerebras is the default host.
Groq hosts the same model and is selected with --provider groq.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

DEFAULT_PROVIDER = "cerebras"


@dataclass(frozen=True)
class Settings:
    provider: str = "Cerebras"
    model: str = "gpt-oss-120b"
    api_key_env: str = "CEREBRAS_API_KEY"
    base_url: Optional[str] = "https://api.cerebras.ai/v1"
    temperature: Optional[float] = 0.0
    top_p: Optional[float] = 1.0
    seed: Optional[int] = 7
    reasoning_effort: str = "medium"
    # Groq hides reasoning with include_reasoning. Cerebras uses reasoning_format.
    include_reasoning: Optional[bool] = None
    reasoning_format: Optional[str] = "hidden"
    max_completion_tokens: int = 8192  # includes reasoning tokens
    structured_output: str = "strict"

    request_timeout_s: float = 90.0
    max_attempts: int = 10
    backoff_base_s: float = 2.0
    backoff_cap_s: float = 60.0
    concurrency: int = 2  # Cerebras free trial is 5 requests/minute

    price_input_per_m: float = 0.35
    price_output_per_m: float = 0.75

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class _Provider:
    name: str
    model: str
    api_key_env: str
    base_url: str
    temperature: float
    top_p: float
    seed: int
    reasoning_effort: str
    include_reasoning: Optional[bool]
    reasoning_format: Optional[str]
    price_input_per_m: float
    price_output_per_m: float


# List prices (input, output) in USD per 1M tokens.
PRICES_PER_M = {
    "gpt-oss-120b": (0.35, 0.75),  # Cerebras list price
    "openai/gpt-oss-120b": (0.15, 0.60),  # Groq list price
    "openai/gpt-oss-20b": (0.075, 0.30),
}

PROVIDERS = {
    "cerebras": _Provider(
        name="Cerebras",
        model="gpt-oss-120b",
        api_key_env="CEREBRAS_API_KEY",
        base_url="https://api.cerebras.ai/v1",
        temperature=0.0,
        top_p=1.0,
        seed=7,
        reasoning_effort="medium",
        include_reasoning=None,
        reasoning_format="hidden",
        price_input_per_m=0.35,
        price_output_per_m=0.75,
    ),
    "groq": _Provider(
        name="Groq",
        model="openai/gpt-oss-120b",
        api_key_env="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1",
        temperature=0.0,
        top_p=1.0,
        seed=7,
        reasoning_effort="medium",
        include_reasoning=False,
        reasoning_format=None,
        price_input_per_m=0.15,
        price_output_per_m=0.60,
    ),
}

SETTINGS = Settings()


def settings_for(provider_id: str, model: Optional[str] = None, concurrency: Optional[int] = None) -> Settings:
    """Settings for one run. An omitted model uses that provider's pinned model."""
    try:
        provider = PROVIDERS[provider_id]
    except KeyError:
        raise ValueError(f"unknown provider {provider_id!r}; choose from {', '.join(PROVIDERS)}") from None
    chosen = model or provider.model
    price_in, price_out = PRICES_PER_M.get(chosen, (provider.price_input_per_m, provider.price_output_per_m))
    return Settings(
        provider=provider.name,
        model=chosen,
        api_key_env=provider.api_key_env,
        base_url=provider.base_url,
        temperature=provider.temperature,
        top_p=provider.top_p,
        seed=provider.seed,
        reasoning_effort=provider.reasoning_effort,
        include_reasoning=provider.include_reasoning,
        reasoning_format=provider.reasoning_format,
        price_input_per_m=price_in,
        price_output_per_m=price_out,
        concurrency=SETTINGS.concurrency if concurrency is None else concurrency,
    )
