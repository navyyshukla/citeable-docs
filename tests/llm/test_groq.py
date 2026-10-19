import json

import httpx
import pytest

from app.llm.base import ProviderError
from app.llm.groq import GroqProvider

OK = {"choices": [{"message": {"content": "yes [a:1]"}, "finish_reason": "stop"}],
      "usage": {"prompt_tokens": 800, "completion_tokens": 40}}


def provider(handler, **kw) -> GroqProvider:
    return GroqProvider("gk", "openai/gpt-oss-20b",
                        httpx.Client(transport=httpx.MockTransport(handler)), **kw)


def test_request_shape_and_parsed_completion():
    seen = {}

    def handler(req):
        seen["url"], seen["auth"] = str(req.url), req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json=OK)

    c = provider(handler).complete("sys", "user", 3000)
    assert c.text == "yes [a:1]" and c.provider == "groq" and c.neurons is None
    assert (c.input_tokens, c.output_tokens) == (800, 40)
    assert seen["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert seen["auth"] == "Bearer gk"
    b = seen["body"]
    assert b["model"] == "openai/gpt-oss-20b" and b["reasoning_effort"] == "low"
    assert b["max_completion_tokens"] == 3000
    assert b["messages"][1] == {"role": "user", "content": "user"}


@pytest.mark.parametrize("status", [429, 500])
def test_http_errors_carry_status(status):
    with pytest.raises(ProviderError) as e:
        provider(lambda r: httpx.Response(status, json={})).complete("s", "u", 5)
    assert e.value.status == status


@pytest.mark.parametrize("choice", [
    {"message": {"content": "cut"}, "finish_reason": "length"},
    {"message": {"content": ""}, "finish_reason": "stop"},
    {"message": {}, "finish_reason": "stop"},
])
def test_truncated_or_empty_answers_fail(choice):
    with pytest.raises(ProviderError):
        provider(lambda r: httpx.Response(200, json={"choices": [choice]})).complete("s", "u", 5)


def test_malformed_body_fails():
    with pytest.raises(ProviderError):
        provider(lambda r: httpx.Response(200, content=b"nope")).complete("s", "u", 5)
    with pytest.raises(ProviderError):
        provider(lambda r: httpx.Response(200, json={"choices": []})).complete("s", "u", 5)
