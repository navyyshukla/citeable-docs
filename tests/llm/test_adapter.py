import pytest

from app.llm.base import Adapter, AllProvidersFailed, Completion, ProviderError


class Fake:
    def __init__(self, name, text=None, error=None, neurons=1.0):
        self.name, self._text, self._error, self._neurons = name, text, error, neurons

    def complete(self, system, user, max_tokens):
        if self._error:
            raise self._error
        return Completion(self._text, self.name, "m", 10, 5, self._neurons, 0.01)


def test_uses_first_provider_and_counts_one_call():
    a = Adapter([Fake("main", "hi"), Fake("backup", "no")])
    out = a.complete("s", "u", 50)
    assert out.text == "hi" and out.provider == "main"
    assert a.calls_made == 1 and a.total_neurons == 1.0


def test_falls_back_when_main_fails():
    a = Adapter([Fake("main", error=ProviderError("429", 429)), Fake("backup", "ok")])
    out = a.complete("s", "u", 50)
    assert out.provider == "backup"
    assert a.calls_made == 2


def test_all_failing_raises_with_every_reason():
    a = Adapter([Fake("a", error=ProviderError("boom a", 500)),
                 Fake("b", error=ProviderError("boom b", None))])
    with pytest.raises(AllProvidersFailed) as e:
        a.complete("s", "u", 50)
    assert "boom a" in str(e.value) and "boom b" in str(e.value)


def test_no_providers_is_an_error():
    with pytest.raises(AllProvidersFailed):
        Adapter([]).complete("s", "u", 50)


def test_neurons_burned_by_a_failed_attempt_count_toward_the_total():
    a = Adapter([Fake("main", error=ProviderError("cut off", neurons=27.0)),
                 Fake("backup", "ok", neurons=1.0)])
    a.complete("s", "u", 50)
    assert a.total_neurons == 28.0


def test_neurons_of_failed_attempts_count_even_when_every_provider_fails():
    a = Adapter([Fake("main", error=ProviderError("cut off", neurons=27.0))])
    with pytest.raises(AllProvidersFailed):
        a.complete("s", "u", 50)
    assert a.total_neurons == 27.0
