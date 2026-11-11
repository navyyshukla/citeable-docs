from datetime import datetime, timedelta, timezone

import pytest

from app.config import load_config
from app.db import DbUnavailable
from app.llm.base import Adapter, Completion, ProviderError
from app.service import AnswerService, AskError
from app.usage import CapHit, Reservation
from ingest.models import Piece

CFG = load_config("config/visidata.yaml")


def mk(i, text):
    slug = i.split(":")[0]
    return Piece(id=i, page_slug=slug, page_title=slug.title(),
                 url=f"https://www.visidata.org/docs/{slug}/", anchor="a",
                 heading_path=(slug.title(), "H"), text=text, docs_ref="stable@abc1234567",
                 docs_version="3.0", last_updated="2026-01-01")


PIECES = [mk("join:0", "Type `&` to join sheets."), mk("rows:0", "Sort rows with `[`.")]


class FakeUsage:
    def __init__(self, cap: CapHit | None = None):
        self.cap, self.reserved, self.finished, self.feedbacks = cap, [], [], []
        self.tokens = {"good": 1, "other": 2}
        self.owner: dict[str, int] = {}

    def token_id_for(self, token):
        return self.tokens.get(token)

    def reserve(self, token_id, project, question, per_visitor, global_cap, neuron_budget):
        if self.cap:
            return self.cap
        rid = f"00000000-0000-0000-0000-{len(self.reserved):012d}"
        self.reserved.append((token_id, question, per_visitor, global_cap, neuron_budget))
        self.owner[rid] = token_id
        return Reservation(rid)

    def finish(self, request_id, **kw):
        self.finished.append((request_id, kw))

    def add_feedback(self, token_id, request_id, rating, comment):
        if rating not in (-1, 1):
            raise ValueError("rating must be 1 or -1")
        if self.owner.get(request_id) != token_id:
            return False
        self.feedbacks.append((request_id, rating, comment))
        return True


class FakeStore:
    def __init__(self, pieces=PIECES, vector_hits=(("join:0", 0.9),), model_ok=True):
        self.pieces, self.vector_hits, self.model_ok = pieces, list(vector_hits), model_ok
        self.loads = 0

    def check_ingest_meta(self, project, model, require=False):
        self.required = require
        if not self.model_ok:
            raise ValueError("pieces were embedded with 'old' but the config says 'new'")

    def load_pieces(self, project):
        self.loads += 1
        return self.pieces

    def vector_search(self, project, vec, k):
        return self.vector_hits


class Fake:
    """Answers the classifier prompt with `label` and every other prompt with `text`."""
    name = "fake"

    def __init__(self, text="It joins sheets [1].", label="normal"):
        self.text, self.label = text, label
        self.calls = self.answer_calls = 0

    def complete(self, system, user, max_tokens, timeout=None):
        self.calls += 1
        if "exactly one word" in system:
            return Completion(self.label, "fake", "m", 50, 2, 2.5, 0.1)
        self.answer_calls += 1
        return Completion(self.text, "fake", "m", 100, 20, 2.5, 0.1)


class FlakyFirst(Fake):
    """The first call (the classifier) fails; later calls work."""

    def complete(self, system, user, max_tokens, timeout=None):
        if self.calls == 0:
            self.calls += 1
            raise ProviderError("503", 503)
        return super().complete(system, user, max_tokens, timeout)


class Down:
    name = "down"

    def complete(self, *a):
        raise ProviderError("503", 503)


def make(usage=None, store=None, provider=None):
    usage, store = usage or FakeUsage(), store or FakeStore()
    provider = provider or Fake()
    made = []

    def make_adapter():
        made.append(1)
        return Adapter([provider])

    svc = AnswerService(CFG, usage, store, make_adapter, embed_query=lambda t: [0.0])
    return svc, usage, store, provider, made


def test_unknown_token_is_401_and_logs_nothing():
    svc, usage, *_ = make()
    with pytest.raises(AskError) as e:
        svc.ask("bad", "what does & do?")
    assert e.value.status == 401
    assert usage.reserved == [] and usage.finished == []


@pytest.mark.parametrize("question", ["", "   ", "x" * 501])
def test_empty_and_long_question_are_400_before_reserve(question):
    svc, usage, *_ = make()
    with pytest.raises(AskError) as e:
        svc.ask("good", question)
    assert e.value.status == 400
    assert usage.reserved == []


def test_cap_hit_is_429_with_reset_time():
    resets = datetime.now(timezone.utc) + timedelta(hours=3)
    svc, usage, store, *_ = make(usage=FakeUsage(cap=CapHit("visitor", resets)))
    with pytest.raises(AskError) as e:
        svc.ask("good", "what does & do?")
    assert e.value.status == 429
    assert "Retry-After" in e.value.headers and int(e.value.headers["Retry-After"]) > 0
    assert store.loads == 0  # no search work for a refused request


def test_happy_path_logs_answer_and_citations():
    svc, usage, *_ = make()
    r = svc.ask("good", "what does & do?")
    assert r.status == "answered" and "joins" in r.text
    assert r.citations[0].url.endswith("/join/")
    assert r.docs_ref == "stable@abc1234567" and r.docs_version == "3.0"
    rid, kw = usage.finished[0]
    assert rid == r.request_id and kw["status"] == "answered"
    assert kw["citations"][0]["url"].endswith("/join/") and kw["llm_calls"] == 2
    assert kw["neurons"] == 5.0 and kw["provider"] == "fake" and kw["docs_ref"] == r.docs_ref
    token_id, question, per_visitor, global_cap, budget = usage.reserved[0]
    assert (per_visitor, global_cap) == (CFG.limits.per_visitor_daily_cap,
                                         CFG.limits.global_daily_cap)
    assert budget == CFG.limits.global_daily_neurons


def test_ask_logs_retrieved_piece_ids():
    svc, usage, *_ = make()
    svc.ask("good", "what does & do?")
    ids = usage.finished[0][1]["retrieved_ids"]
    assert ids and ids[0] == "join:0"  # rank order: the piece about `&` comes first
    assert set(ids) <= {p.id for p in PIECES}


def test_below_threshold_abstains_without_adapter_call():
    store = FakeStore(vector_hits=(("rows:0", 0.5),))  # found by one search only: 1/61
    svc, usage, _, provider, made = make(store=store)
    r = svc.ask("good", "zzzz nothing")
    assert r.status == "abstained" and provider.answer_calls == 0  # no answer call, only the classifier
    assert usage.finished[0][1]["status"] == "abstained" and usage.finished[0][1]["llm_calls"] == 1


def test_all_providers_failed_is_503_and_logged_as_error():
    svc, usage, *_ = make(provider=Down())
    with pytest.raises(AskError) as e:
        svc.ask("good", "what does & do?")
    assert e.value.status == 503
    rid, kw = usage.finished[0]
    assert kw["status"] == "error" and "503" in kw["error"]


def test_unexpected_error_is_logged_then_raised():
    store = FakeStore()
    store.vector_search = lambda *a: (_ for _ in ()).throw(RuntimeError("db exploded"))
    svc, usage, *_ = make(store=store)
    with pytest.raises(RuntimeError):
        svc.ask("good", "what does & do?")
    assert usage.finished[0][1]["status"] == "error"


def test_each_request_gets_its_own_adapter():
    svc, _, _, _, made = make()
    svc.ask("good", "what does & do?")
    svc.ask("good", "what does & do?")
    assert len(made) == 2


def test_index_loaded_once_across_requests():
    svc, _, store, *_ = make()
    svc.ask("good", "what does & do?")
    svc.ask("good", "what does & do?")
    assert store.loads == 1


def test_model_mismatch_refuses_to_serve():
    svc, usage, *_ = make(store=FakeStore(model_ok=False))
    with pytest.raises(AskError) as e:
        svc.ask("good", "what does & do?")
    assert e.value.status == 503 and "index" in e.value.message.lower()
    assert usage.finished[0][1]["status"] == "error"


def test_empty_database_is_503_not_a_crash():
    svc, *_ = make(store=FakeStore(pieces=[]))
    with pytest.raises(AskError) as e:
        svc.ask("good", "what does & do?")
    assert e.value.status == 503


def test_feedback_for_other_tokens_request_is_404():
    svc, usage, *_ = make()
    r = svc.ask("good", "what does & do?")
    with pytest.raises(AskError) as e:
        svc.feedback("other", r.request_id, 1, None)
    assert e.value.status == 404
    svc.feedback("good", r.request_id, -1, "wrong key")
    assert usage.feedbacks == [(r.request_id, -1, "wrong key")]


def test_feedback_bad_token_and_bad_rating():
    svc, *_ = make()
    r = svc.ask("good", "what does & do?")
    with pytest.raises(AskError) as e:
        svc.feedback("bad", r.request_id, 1, None)
    assert e.value.status == 401
    with pytest.raises(AskError) as e:
        svc.feedback("good", r.request_id, 7, None)
    assert e.value.status == 400


def test_neurons_burned_by_failed_attempts_are_logged_for_the_neuron_cap():
    class CutOff:
        name = "cutoff"

        def complete(self, *a):
            raise ProviderError("length", 200, neurons=40.0)

    svc, usage, *_ = make(provider=CutOff())
    with pytest.raises(AskError):
        svc.ask("good", "what does & do?")
    kw = usage.finished[0][1]
    # the classifier call burned 40 and failed open to "normal"; the answer call burned 40 more
    assert kw["status"] == "error" and kw["neurons"] == 80.0 and kw["llm_calls"] == 2


def test_version_needs_no_database_and_shows_docs_ref_once_loaded():
    svc, _, store, *_ = make()
    v = svc.version()
    assert v["project"] == "visidata" and v["docs_ref"] is None and store.loads == 0
    assert v["models"] == CFG.models.answer_order
    svc.ask("good", "what does & do?")
    assert svc.version()["docs_ref"] == "stable@abc1234567"


class CutOffThenAnswer:
    """Two providers in one: the first burns 40 neurons and fails, the second answers."""

    def __init__(self):
        self.providers = [self._cut(), Fake("It joins sheets [1].")]

    @staticmethod
    def _cut():
        class CutOff:
            name = "cutoff"

            def complete(self, *a):
                raise ProviderError("length", 200, neurons=40.0)
        return CutOff()


def test_neurons_of_failed_fallbacks_count_when_a_later_provider_answers():
    usage, store = FakeUsage(), FakeStore()
    svc = AnswerService(CFG, usage, store, lambda: Adapter(CutOffThenAnswer().providers),
                        embed_query=lambda t: [0.0])
    svc.ask("good", "what does & do?")
    kw = usage.finished[0][1]
    # each of the two model calls (classifier, answer) first hit the cut-off provider, then Fake
    assert kw["status"] == "answered" and kw["llm_calls"] == 4
    assert kw["neurons"] == pytest.approx(85.0)  # 2 x (40 burned by the failure + 2.5 by the reply)


@pytest.mark.parametrize("question", ["a\x00b", "\ud800", "ok \udfff"])
def test_nul_and_lone_surrogates_are_a_400_not_a_database_crash(question):
    svc, usage, *_ = make()
    with pytest.raises(AskError) as e:
        svc.ask("good", question)
    assert e.value.status == 400 and usage.reserved == []


def test_database_down_during_search_is_a_503_and_the_original_error_survives():
    store = FakeStore()
    store.vector_search = lambda *a: (_ for _ in ()).throw(DbUnavailable("down"))
    usage = FakeUsage()
    usage.finish = lambda *a, **k: (_ for _ in ()).throw(DbUnavailable("still down"))
    svc, *_ = make(usage=usage, store=store)
    with pytest.raises(AskError) as e:
        svc.ask("good", "what does & do?")
    assert e.value.status == 503


def test_database_down_when_logging_the_answer_still_returns_the_answer():
    usage = FakeUsage()
    usage.finish = lambda *a, **k: (_ for _ in ()).throw(DbUnavailable("down"))
    svc, *_ = make(usage=usage)
    assert svc.ask("good", "what does & do?").status == "answered"


def test_database_down_at_reserve_or_feedback_is_a_503():
    usage = FakeUsage()
    usage.reserve = lambda *a, **k: (_ for _ in ()).throw(DbUnavailable("down"))
    svc, *_ = make(usage=usage)
    with pytest.raises(AskError) as e:
        svc.ask("good", "what does & do?")
    assert e.value.status == 503
    usage2 = FakeUsage()
    usage2.add_feedback = lambda *a, **k: (_ for _ in ()).throw(DbUnavailable("down"))
    svc2, *_ = make(usage=usage2)
    with pytest.raises(AskError) as e:
        svc2.feedback("good", "rid", 1, None)
    assert e.value.status == 503


def test_the_service_demands_an_ingest_meta_row_before_serving():
    svc, usage, store, *_ = make()
    svc.ask("good", "what does & do?")
    assert store.required is True


def test_card_question_returns_a_card_without_search():
    svc, usage, store, provider, _ = make(provider=Fake(label="about"))
    r = svc.ask("good", "what is visidata")
    assert r.status == "card" and r.kind == "about" and r.text == ""
    assert r.citations == [] and r.closest == []
    assert store.loads == 0  # a card never loads the docs index, even on a cold server
    assert provider.calls == 1 and provider.answer_calls == 0


def test_card_row_is_logged():
    svc, usage, *_ = make(provider=Fake(label="help"))
    r = svc.ask("good", "what can you do?")
    rid, kw = usage.finished[0]
    assert rid == r.request_id and kw["status"] == "card" and kw["answer_text"] == "card:help"
    assert kw["llm_calls"] == 1 and kw["neurons"] == 2.5 and kw["citations"] == []
    assert kw.get("retrieved_ids") is None and kw["error"] is None
    assert (kw["provider"], kw["model"]) == ("fake", "m")  # who classified, so the beta can see


def test_classifier_failure_falls_through_to_the_normal_answer():
    svc, usage, _, provider, _ = make(provider=FlakyFirst())
    r = svc.ask("good", "what does & do?")
    assert r.status == "answered" and r.kind is None
    assert usage.finished[0][1]["llm_calls"] == 2


def test_all_providers_down_is_the_usual_503_message():
    svc, usage, *_ = make(provider=Down())
    with pytest.raises(AskError) as e:
        svc.ask("good", "what does & do?")
    assert e.value.status == 503 and e.value.message == "The answer models are busy. Try again in a minute."
    assert usage.finished[0][1]["status"] == "error"  # the classifier error never reaches the visitor


def test_normal_question_logs_classifier_and_answer_together():
    svc, usage, *_ = make()
    svc.ask("good", "what does & do?")
    kw = usage.finished[0][1]
    assert kw["llm_calls"] == 2 and kw["neurons"] == 5.0  # the neuron cap sees the true spend


def test_cap_hit_stops_before_the_classifier_runs():
    resets = datetime.now(timezone.utc) + timedelta(hours=3)
    svc, _, _, provider, _ = make(usage=FakeUsage(cap=CapHit("visitor", resets)))
    with pytest.raises(AskError):
        svc.ask("good", "what is visidata")
    assert provider.calls == 0
