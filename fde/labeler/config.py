"""Pinned generation and runtime settings. Recorded verbatim in every debug record."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Settings:
    model: str = "openai/gpt-oss-120b"
    temperature: float = 0.0
    top_p: float = 1.0
    seed: int = 7
    reasoning_effort: str = "medium"
    max_completion_tokens: int = 8192  # includes reasoning tokens
    structured_output: str = "strict"  # "strict" json_schema; "json_object" for models without it

    request_timeout_s: float = 90.0
    max_attempts: int = 6
    backoff_base_s: float = 2.0
    backoff_cap_s: float = 60.0
    concurrency: int = 4

    # Groq list prices (USD per 1M tokens) for the pinned model, used for cost reporting only.
    price_input_per_m: float = 0.15
    price_output_per_m: float = 0.60

    def as_dict(self) -> dict:
        return asdict(self)


SETTINGS = Settings()
