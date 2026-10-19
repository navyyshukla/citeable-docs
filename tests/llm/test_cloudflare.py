import json

import httpx
import pytest

from app.llm.base import ProviderError
from app.llm.cloudflare import CloudflareClient, CloudflareProvider, embed_texts

CHAT_OK = {"success": True, "result": {"response": "hello [1]",
           "usage": {"prompt_tokens": 1000, "completion_tokens": 100}}}


def gemma_reply(content="hi [a:1]", finish="stop", usage=None):
    return {"result": {"choices": [{"message": {"content": content}, "finish_reason": finish}],
                       "usage": usage or {"prompt_tokens": 500, "completion_tokens": 50,
                                          "neurons": 3.5}}}


def client_with(handler) -> CloudflareClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return CloudflareClient("acct", "tok", http)


def test_chat_parses_text_usage_and_neurons():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=CHAT_OK)

    p = CloudflareProvider(client_with(handler), "@cf/meta/m", price=(4000.0, 30000.0))
    c = p.complete("sys", "user", 50)
    assert c.text == "hello [1]" and c.input_tokens == 1000 and c.output_tokens == 100
    assert c.neurons == pytest.approx(1000 / 1e6 * 4000 + 100 / 1e6 * 30000)
    assert seen["url"].endswith("/accounts/acct/ai/run/@cf/meta/m")
    assert seen["auth"] == "Bearer tok"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["body"]["max_tokens"] == 50
    assert "chat_template_kwargs" not in seen["body"]


def test_choices_shape_is_parsed_and_reported_neurons_win_over_price():
    p = CloudflareProvider(client_with(lambda r: httpx.Response(200, json=gemma_reply())),
                           "g", price=(9091.0, 27273.0))
    c = p.complete("s", "u", 50)
    assert c.text == "hi [a:1]" and c.neurons == 3.5
    assert (c.input_tokens, c.output_tokens) == (500, 50)


@pytest.mark.parametrize("finish", ["length", None, "tool_calls"])
def test_finish_reason_other_than_stop_is_a_failure(finish):
    body = gemma_reply(finish=finish)
    p = CloudflareProvider(client_with(lambda r: httpx.Response(200, json=body)), "g")
    with pytest.raises(ProviderError, match="finish_reason"):
        p.complete("s", "u", 50)


@pytest.mark.parametrize("content", ["", "   ", None])
def test_empty_answer_is_a_failure_in_both_shapes(content):
    p = CloudflareProvider(client_with(lambda r: httpx.Response(200, json=gemma_reply(content))), "g")
    with pytest.raises(ProviderError, match="empty"):
        p.complete("s", "u", 50)
    legacy = {"result": {"response": content}}
    p = CloudflareProvider(client_with(lambda r: httpx.Response(200, json=legacy)), "l")
    with pytest.raises(ProviderError, match="empty"):
        p.complete("s", "u", 50)


def test_thinking_flag_is_sent_only_when_configured():
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json=gemma_reply())

    CloudflareProvider(client_with(handler), "g", thinking=False).complete("s", "u", 50)
    CloudflareProvider(client_with(handler), "g", thinking=True).complete("s", "u", 50)
    assert bodies[0]["chat_template_kwargs"] == {"enable_thinking": False}
    assert bodies[1]["chat_template_kwargs"] == {"enable_thinking": True}


def test_provider_cap_limits_the_request_but_never_raises_it():
    bodies = []

    def handler(req):
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json=CHAT_OK)

    p = CloudflareProvider(client_with(handler), "l", max_tokens_cap=400)
    p.complete("s", "u", 3000)
    p.complete("s", "u", 100)
    assert [b["max_tokens"] for b in bodies] == [400, 100]


@pytest.mark.parametrize("status", [429, 500, 503])
def test_http_errors_become_provider_errors_with_status(status):
    p = CloudflareProvider(client_with(lambda r: httpx.Response(status, json={})), "m")
    with pytest.raises(ProviderError) as e:
        p.complete("s", "u", 5)
    assert e.value.status == status


def test_network_error_becomes_provider_error():
    def boom(req):
        raise httpx.ConnectTimeout("slow")

    with pytest.raises(ProviderError, match="network"):
        CloudflareProvider(client_with(boom), "m").complete("s", "u", 5)


def test_malformed_json_becomes_provider_error():
    p = CloudflareProvider(client_with(lambda r: httpx.Response(200, content=b"<html>")), "m")
    with pytest.raises(ProviderError):
        p.complete("s", "u", 5)


def test_missing_response_field_becomes_provider_error():
    p = CloudflareProvider(client_with(lambda r: httpx.Response(200, json={"result": {}})), "m")
    with pytest.raises(ProviderError):
        p.complete("s", "u", 5)


def test_embed_texts_batches_and_preserves_order():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        texts = json.loads(req.content)["text"]
        calls.append(len(texts))
        return httpx.Response(200, json={"result": {"data": [[float(len(t))] for t in texts]}})

    out = embed_texts(client_with(handler), "emb", ["a", "bb", "ccc", "dddd", "e"], batch=2)
    assert calls == [2, 2, 1]
    assert out == [[1.0], [2.0], [3.0], [4.0], [1.0]]


def test_embed_texts_cuts_input_at_2000_chars():
    seen = []

    def handler(req):
        seen.extend(json.loads(req.content)["text"])
        return httpx.Response(200, json={"result": {"data": [[0.0]]}})

    embed_texts(client_with(handler), "emb", ["x" * 5000], batch=1)
    assert [len(t) for t in seen] == [2000]


def test_embed_wrong_shape_is_an_error():
    c = client_with(lambda r: httpx.Response(200, json={"result": {"data": []}}))
    with pytest.raises(ProviderError):
        embed_texts(c, "emb", ["a"], batch=1)
