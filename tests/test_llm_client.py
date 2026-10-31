import json

import httpx
import pytest

from app.services.llm_client import GroqClient, LLMError


def make_client(handler):
    return GroqClient(
        "key", "model", transport=httpx.MockTransport(handler), retry_delay=0
    )


def ok_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


async def test_returns_parsed_json_and_sends_expected_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return ok_response('{"a": 1}')

    client = make_client(handler)
    assert await client.complete_json("sys", "usr") == {"a": 1}
    assert seen["auth"] == "Bearer key"
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["messages"][1] == {"role": "user", "content": "usr"}


async def test_retries_on_429():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(429) if len(calls) == 1 else ok_response("{}")

    assert await make_client(handler).complete_json("s", "u") == {}
    assert len(calls) == 2


async def test_gives_up_after_three_429():
    client = make_client(lambda request: httpx.Response(429))
    with pytest.raises(LLMError):
        await client.complete_json("s", "u")


async def test_server_error_becomes_llm_error():
    client = make_client(lambda request: httpx.Response(500))
    with pytest.raises(LLMError):
        await client.complete_json("s", "u")


async def test_invalid_json_becomes_llm_error():
    client = make_client(lambda request: ok_response("not json"))
    with pytest.raises(LLMError):
        await client.complete_json("s", "u")