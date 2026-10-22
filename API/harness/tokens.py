"""Token usage accounting and USD cost calculation per turn for the API harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from shared.config import DEFAULT_MODEL, MODEL_PRICING_USD_PER_M


@dataclass
class TurnTokenMetrics:
    """Aggregated token and cost metrics for a single user turn."""

    input_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    tools_used: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    duration_seconds: float = 0.0

    def record_response_usage(self, usage: Any, model: str = DEFAULT_MODEL) -> None:
        """Accumulate usage from a single Anthropic Messages API response."""
        inp = int(getattr(usage, "input_tokens", 0) or 0)
        cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        cache_write = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        out = int(getattr(usage, "output_tokens", 0) or 0)

        self.input_tokens += inp
        self.cache_read_tokens += cache_read
        self.cache_write_tokens += cache_write
        self.output_tokens += out
        self.model_calls += 1

        call_cost = compute_cost_usd(
            input_tokens=inp,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            output_tokens=out,
            model=model,
        )
        self.cost_usd = round(self.cost_usd + call_cost, 6)
        print(
            f"[tokens.py] Recorded API call #{self.model_calls}: "
            f"in={inp}, cache_read={cache_read}, cache_write={cache_write}, "
            f"out={out}, call_cost=${call_cost:.6f}"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize turn metrics to the benchmark JSON format."""
        print(
            f"[tokens.py] Finalized turn metrics: calls={self.model_calls}, "
            f"in={self.input_tokens}, cache_read={self.cache_read_tokens}, "
            f"cache_write={self.cache_write_tokens}, out={self.output_tokens}, "
            f"cost=${self.cost_usd:.6f}, time={self.duration_seconds:.3f}s"
        )
        return {
            "input_tokens": self.input_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "output_tokens": self.output_tokens,
            "model_calls": self.model_calls,
            "tools_used": list(self.tools_used),
            "cost_usd": round(self.cost_usd, 6),
            "duration_seconds": round(self.duration_seconds, 4),
        }


def compute_cost_usd(
    input_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
    output_tokens: int,
    model: str = DEFAULT_MODEL,
) -> float:
    """Compute USD cost for the given token counts using official pricing per 1M tokens."""
    rates = MODEL_PRICING_USD_PER_M.get(
        model,
        MODEL_PRICING_USD_PER_M[DEFAULT_MODEL],
    )
    cost = (
        (input_tokens * rates["input"])
        + (cache_read_tokens * rates["cache_read"])
        + (cache_write_tokens * rates["cache_write"])
        + (output_tokens * rates["output"])
    ) / 1_000_000.0
    return round(cost, 6)
