import json

import httpx
import pytest

from app.config import load_config
from app.llm.base import ProviderError
from app.llm.build import build_adapter
from app.llm.gemini import GeminiProvider

OK = {"candidates": [{"content": {"parts": [{"text": '{"grounded": true}'}]},
                      "finishReason": "STOP"}],
      "usageMetadata": {"promptTokenCount": 300, "candidatesTokenCount": 12}}


def provider(handler, **kw) -> GeminiProvider:
    return GeminiProvider("gem-key", client=httpx.Client(transport=httpx.MockTransport(handler)),
                          **kw)


def test_request_shape_and_parsed_completion():
    seen = {}

    def handler(req):
        seen["url"], seen["key"] = str(req.url), req.headers.get("x-goog-api-key")
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=OK)

    c = provider(handler).complete("sys", "user", 300)
    assert c.text == '{"grounded": true}' and c.provider == "gemini" and c.neurons is None
    assert (c.input_tokens, c.output_tokens) == (300, 12)
    assert seen["url"] == ("https://generativelanguage.googleapis.com/v1beta/models/"
                           "gemini-3.5-flash-lite:generateContent")
    assert seen["key"] == "gem-key" and "gem-key" not in seen["url"]  # keys stay out of URLs
    b = seen["body"]
    assert b["systemInstruction"]["parts"][0]["text"] == "sys"
    assert b["contents"] == [{"role": "user", "parts": [{"text": "user"}]}]
    assert b["generationConfig"]["maxOutputTokens"] == 300
    assert "responseMimeType" not in b["generationConfig"]


def test_json_output_mode_asks_for_json():
    seen = {}

    def handler(req):
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=OK)

    provider(handler, json_output=True).complete("s", "u", 50)
    assert seen["body"]["generationConfig"]["responseMimeType"] == "application/json"


@pytest.mark.parametrize("status", [429, 500])
def test_non_200_is_a_provider_error_with_status(status):
    with pytest.raises(ProviderError) as e:
        provider(lambda r: httpx.Response(status, json={})).complete("s", "u", 5)
    assert e.value.status == status


@pytest.mark.parametrize("body", [
    {"candidates": [{"content": {"parts": [{"text": "  "}]}, "finishReason": "STOP"}]},
    {"candidates": [{"content": {"parts": [{"text": "cut"}]}, "finishReason": "MAX_TOKENS"}]},
    {"candidates": []},
    {"promptFeedback": {"blockReason": "SAFETY"}},
    {},
])
def test_empty_cut_off_blocked_or_malformed_answers_are_provider_errors(body):
    with pytest.raises(ProviderError):
        provider(lambda r: httpx.Response(200, json=body)).complete("s", "u", 5)


def test_network_error_is_a_provider_error():
    def boom(req):
        raise httpx.ConnectError("down")

    with pytest.raises(ProviderError):
        provider(boom).complete("s", "u", 5)


def test_gemini_cannot_be_in_the_user_answer_chain():
    cfg = load_config("config/visidata.yaml")
    bad = cfg.model_copy(update={"models": cfg.models.model_copy(
        update={"answer_order": ["gemini:gemini-3.5-flash-lite"]})})
    with pytest.raises(ValueError, match="gemini"):
        build_adapter(bad, {"GEMINI_API_KEY": "k"})
