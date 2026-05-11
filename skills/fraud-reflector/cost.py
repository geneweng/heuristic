"""Token + cost tracking for live reflector calls.

Rates are the published Anthropic prices for the listed models, USD per million
tokens. Update if pricing changes; the field is logged so old runs remain
auditable against the rates at the time.
"""

from dataclasses import dataclass

TOKEN_RATES_USD_PER_M = {
    "claude-opus-4-7":   {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0,  "output": 15.0},
    "claude-haiku-4-5":  {"input": 0.80, "output": 4.0},
}


@dataclass(frozen=True)
class Usage:
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def cost_usd(self) -> float:
        rates = TOKEN_RATES_USD_PER_M.get(self.model)
        if not rates:
            return 0.0
        return (
            self.input_tokens * rates["input"] / 1_000_000
            + self.output_tokens * rates["output"] / 1_000_000
        )

    def as_dict(self) -> dict:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
        }
