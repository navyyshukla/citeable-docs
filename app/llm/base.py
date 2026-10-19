from dataclasses import dataclass
from typing import Protocol


class ProviderError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class AllProvidersFailed(Exception):
    pass


@dataclass(frozen=True)
class Completion:
    text: str
    provider: str
    model: str
    input_tokens: int | None
    output_tokens: int | None
    neurons: float | None
    seconds: float


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str, max_tokens: int) -> Completion: ...


def check_answer(text: object, finish_reason: object) -> str:
    """An answer counts only if it has text and the model stopped on its own."""
    if finish_reason != "stop":
        raise ProviderError(f"finish_reason {finish_reason!r}, not 'stop'")
    if not isinstance(text, str) or not text.strip():
        raise ProviderError("empty answer")
    return text.strip()


class Adapter:
    """Try providers in order. Every attempt counts as a call (quota burns on failures too)."""

    def __init__(self, providers: list[Provider]):
        self.providers = providers
        self.calls_made = 0
        self.total_neurons = 0.0

    def complete(self, system: str, user: str, max_tokens: int) -> Completion:
        if not self.providers:
            raise AllProvidersFailed("no providers configured")
        errors: list[str] = []
        for p in self.providers:
            self.calls_made += 1
            try:
                c = p.complete(system, user, max_tokens)
            except ProviderError as e:
                label = f"{p.name}:{getattr(p, 'model', '?')}"
                errors.append(f"{label}: {e}")
                continue
            self.total_neurons += c.neurons or 0.0
            return c
        raise AllProvidersFailed("; ".join(errors))
