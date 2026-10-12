"""
Tests for the LLM provider layer.

These exist because the original suite only exercised MockLLMClient, which has
hardcoded responses. The real Ollama path was silently broken (it read a
``self.responses`` attribute that does not exist), and no test could catch it.
These tests drive the real request-building and response-parsing code with a
stubbed transport, so a regression fails here instead of degrading every
generated design into a rule-based template.
"""

import json

import httpx
import pytest

from src.llm.providers import (
    LLMMessage,
    LLMResponseError,
    OllamaClient,
    OpenAIClient,
    extract_json_object,
)


class TestExtractJsonObject:
    """`extract_json_object` must tolerate what models actually return."""

    def test_plain_json(self):
        assert extract_json_object('{"a": 1}') == {"a": 1}

    def test_json_inside_markdown_fence(self):
        text = 'Here is the circuit:\n```json\n{"topology": "ldo"}\n```\nHope that helps!'
        assert extract_json_object(text) == {"topology": "ldo"}

    def test_json_inside_unlabelled_fence(self):
        text = "```\n{\"a\": {\"b\": 2}}\n```"
        assert extract_json_object(text) == {"a": {"b": 2}}

    def test_json_with_surrounding_prose(self):
        text = 'Sure! {"components": []} Let me know if you need more.'
        assert extract_json_object(text) == {"components": []}

    def test_empty_response_raises(self):
        with pytest.raises(LLMResponseError):
            extract_json_object("")

    def test_whitespace_response_raises(self):
        with pytest.raises(LLMResponseError):
            extract_json_object("   \n  ")

    def test_non_json_raises(self):
        with pytest.raises(LLMResponseError):
            extract_json_object("I cannot help with that request.")

    def test_json_array_rejected_with_clear_message(self):
        with pytest.raises(LLMResponseError, match="array"):
            extract_json_object('[{"a": 1}]')


class _StubTransport(httpx.AsyncBaseTransport):
    """Captures requests and returns a canned Ollama-shaped response."""

    def __init__(self, content: str = '{"ok": true}', status: int = 200):
        self.content = content
        self.status = status
        self.requests = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode()) if request.content else {}
        self.requests.append((str(request.url), body))
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "boom"})
        return httpx.Response(
            200,
            json={
                "model": body.get("model", ""),
                "message": {"role": "assistant", "content": self.content},
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 11,
                "eval_count": 22,
            },
        )


def _ollama_with_stub(transport: _StubTransport) -> OllamaClient:
    client = OllamaClient(model="qwen2.5:3b", base_url="http://ollama.test")
    client._client = httpx.AsyncClient(
        transport=transport, base_url="http://ollama.test", timeout=5.0
    )
    return client


class TestOllamaClient:
    """The real Ollama client must POST to /api/chat and parse the message."""

    @pytest.mark.asyncio
    async def test_complete_posts_to_chat_endpoint(self):
        transport = _StubTransport('{"topology": "ldo"}')
        client = _ollama_with_stub(transport)

        response = await client.complete(
            [LLMMessage(role="user", content="design an LDO")]
        )

        assert response.content == '{"topology": "ldo"}'
        assert response.model == "qwen2.5:3b"
        assert response.usage["completion_tokens"] == 22

        url, body = transport.requests[0]
        assert url.endswith("/api/chat")
        assert body["stream"] is False
        assert body["messages"] == [{"role": "user", "content": "design an LDO"}]

    @pytest.mark.asyncio
    async def test_complete_accepts_bare_string(self):
        transport = _StubTransport('{"ok": true}')
        client = _ollama_with_stub(transport)

        await client.complete("hello")

        _, body = transport.requests[0]
        assert body["messages"] == [{"role": "user", "content": "hello"}]

    @pytest.mark.asyncio
    async def test_complete_structured_sends_schema_as_format(self):
        transport = _StubTransport('{"topology": "ldo", "components": []}')
        client = _ollama_with_stub(transport)
        schema = {"type": "object", "properties": {"topology": {"type": "string"}}}

        result = await client.complete_structured(
            [LLMMessage(role="user", content="spec please")], schema
        )

        assert result == {"topology": "ldo", "components": []}
        _, body = transport.requests[0]
        # The bare schema must be passed, not an OpenAI-style wrapper.
        assert body["format"] == schema

    @pytest.mark.asyncio
    async def test_complete_structured_parses_fenced_json(self):
        transport = _StubTransport('```json\n{"topology": "buck"}\n```')
        client = _ollama_with_stub(transport)

        result = await client.complete_structured(
            [LLMMessage(role="user", content="x")], {"type": "object"}
        )

        assert result == {"topology": "buck"}

    @pytest.mark.asyncio
    async def test_empty_message_raises(self):
        transport = _StubTransport("")
        client = _ollama_with_stub(transport)

        with pytest.raises(LLMResponseError):
            await client.complete([LLMMessage(role="user", content="x")])

    @pytest.mark.asyncio
    async def test_structured_format_rejection_falls_back_to_unconstrained(self):
        """Older Ollama builds reject `format`; retry without it."""

        class _RejectingTransport(httpx.AsyncBaseTransport):
            def __init__(self):
                self.calls = []

            async def handle_async_request(self, request):
                body = json.loads(request.content.decode())
                self.calls.append(body)
                if "format" in body:
                    return httpx.Response(400, json={"error": "format unsupported"})
                return httpx.Response(
                    200,
                    json={
                        "model": "qwen2.5:3b",
                        "message": {"role": "assistant", "content": '{"ok": 1}'},
                        "done": True,
                    },
                )

        transport = _RejectingTransport()
        client = OllamaClient(model="qwen2.5:3b", base_url="http://ollama.test")
        client._client = httpx.AsyncClient(
            transport=transport, base_url="http://ollama.test", timeout=5.0
        )

        result = await client.complete_structured(
            [LLMMessage(role="user", content="x")], {"type": "object"}
        )

        assert result == {"ok": 1}
        assert len(transport.calls) == 2
        assert "format" in transport.calls[0]
        assert "format" not in transport.calls[1]


class TestOpenAIClient:
    """OpenAI-compatible endpoints (NVIDIA NIM, Groq, OpenRouter, ...)."""

    class _Transport(httpx.AsyncBaseTransport):
        def __init__(self, content: str):
            self.content = content
            self.requests = []

        async def handle_async_request(self, request):
            self.requests.append(json.loads(request.content.decode()))
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": self.content}, "finish_reason": "stop"}
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2},
                },
            )

    def _client(self, content: str) -> OpenAIClient:
        transport = self._Transport(content)
        client = OpenAIClient(api_key="test", base_url="http://openai.test/v1")
        client._client = httpx.AsyncClient(
            transport=transport, base_url="http://openai.test/v1", timeout=5.0
        )
        client._transport = transport
        return client

    @pytest.mark.asyncio
    async def test_complete_parses_choice(self):
        client = self._client('{"a": 1}')
        response = await client.complete([LLMMessage(role="user", content="hi")])
        assert response.content == '{"a": 1}'

    @pytest.mark.asyncio
    async def test_complete_structured_handles_fenced_json(self):
        client = self._client('```json\n{"topology": "ldo"}\n```')
        result = await client.complete_structured(
            [LLMMessage(role="user", content="x")], {"type": "object"}
        )
        assert result == {"topology": "ldo"}
