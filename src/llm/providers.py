"""
LLM Provider Abstraction for AI-Powered Electronics Design Platform.

Supports multiple LLM providers (Ollama, OpenAI, Anthropic) with a unified interface.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Union

import httpx

logger = logging.getLogger(__name__)


class LLMResponseError(RuntimeError):
    """Raised when a provider returns content that cannot be used."""


_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def extract_json_object(text: str) -> Dict[str, Any]:
    """
    Extract a JSON object from raw LLM text.

    Local and instruction-tuned models frequently wrap JSON in prose or
    markdown fences even when asked not to. This tolerates that instead of
    failing the whole pipeline on a stray ```json line.

    Raises:
        LLMResponseError: if no parseable JSON object can be found.
    """
    if not text or not text.strip():
        raise LLMResponseError("LLM returned an empty response")

    stripped = text.strip()
    # An array is a different contract; reject it explicitly rather than trying
    # to coerce its first object into a dict.
    if stripped.startswith("[") and stripped.endswith("]"):
        raise LLMResponseError(
            "LLM returned a JSON array where a JSON object was required"
        )

    candidates: List[str] = [stripped]

    # Prefer the contents of the first fenced code block, if present.
    for match in _FENCE_RE.finditer(text):
        fenced = match.group(1).strip()
        if fenced:
            candidates.append(fenced)

    # Fall back to the outermost {...} span.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])

    saw_list = False
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            saw_list = True

    if saw_list:
        raise LLMResponseError(
            "LLM returned a JSON array where a JSON object was required"
        )
    preview = text.strip()[:300]
    raise LLMResponseError(f"Could not parse JSON object from LLM response: {preview!r}")


class LLMProvider(Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MOCK = "mock"


@dataclass
class LLMMessage:
    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    content: str
    usage: Optional[Dict[str, int]] = None
    model: str = ""
    finish_reason: str = ""


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    async def complete(
        self,
        messages: Union[List[LLMMessage], str],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """Generate completion from messages."""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the LLM service is available."""
        pass


class OllamaClient(LLMClient):
    """Ollama local LLM client."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3.1:8b",
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout, base_url=self.base_url
            )
        return self._client

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            response = await client.get(f"{self.base_url}/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False

    async def complete(
        self,
        messages: Union[List[LLMMessage], str],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """Call the Ollama /api/chat endpoint."""
        client = await self._get_client()

        if isinstance(messages, str):
            normalized = [LLMMessage(role="user", content=messages)]
        else:
            normalized = list(messages)

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in normalized],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }

        # Ollama accepts a JSON schema in `format` to constrain decoding.
        if response_format:
            schema = self._schema_from_response_format(response_format)
            if schema is not None:
                payload["format"] = schema

        try:
            response = await client.post("/api/chat", json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError as e:
            # Older Ollama builds reject structured `format`; retry unconstrained.
            if "format" in payload:
                logger.warning(
                    "Ollama rejected structured format (%s); retrying without it",
                    e.response.status_code,
                )
                payload.pop("format", None)
                response = await client.post(
                    "/api/chat", json=payload, timeout=self.timeout
                )
                response.raise_for_status()
                data = response.json()
            else:
                logger.error(f"Ollama completion failed: {e}")
                raise
        except Exception as e:
            logger.error(f"Ollama completion failed: {e}")
            raise

        message = data.get("message") or {}
        content = message.get("content")
        if content is None:
            content = data.get("response", "")

        if not content:
            raise LLMResponseError(
                f"Ollama returned an empty message for model {self.model}"
            )

        return LLMResponse(
            content=content,
            usage={
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
            },
            model=data.get("model", self.model),
            finish_reason=data.get("done_reason", ""),
        )

    @staticmethod
    def _schema_from_response_format(
        response_format: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Extract a bare JSON schema from an OpenAI-style response_format."""
        if "json_schema" in response_format:
            inner = response_format["json_schema"]
            if isinstance(inner, dict):
                return inner.get("schema", inner)
            return inner
        if response_format.get("type") == "json_object":
            return None
        return response_format

    async def complete_structured(
        self,
        messages: List[LLMMessage],
        response_schema: Dict[str, Any],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """Generate schema-constrained JSON output via Ollama's `format` field."""
        response = await self.complete(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_schema", "json_schema": response_schema},
        )
        return extract_json_object(response.content)


class OpenAIClient(LLMClient):
    """OpenAI API client."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.api_key}"},
                base_url=self.base_url,
            )
        return self._client

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            response = await client.get("/models", timeout=10.0)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"OpenAI health check failed: {e}")
            return False

    async def complete(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        client = await self._get_client()

        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format:
            payload["response_format"] = response_format

        try:
            response = await client.post(
                "/chat/completions",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            choice = data["choices"][0]
            return LLMResponse(
                content=choice["message"]["content"],
                usage=data.get("usage"),
                model=self.model,
                finish_reason=choice.get("finish_reason"),
            )
        except Exception as e:
            logger.error(f"OpenAI completion failed: {e}")
            raise

    async def complete_structured(
        self,
        messages: List[LLMMessage],
        response_schema: Dict[str, Any],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        response = await self.complete(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_output",
                    "schema": response_schema,
                    "strict": True,
                },
            },
        )
        return extract_json_object(response.content)

    async def health_check(self) -> bool:
        try:
            client = await self._get_client()
            response = await client.get("/models", timeout=10.0)
            return response.status_code == 200
        except Exception:
            return False


class AnthropicClient(LLMClient):
    """Anthropic Claude API client."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        base_url: str = "https://api.anthropic.com",
        timeout: float = 120.0,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                base_url=self.base_url,
            )
        return self._client

    async def health_check(self) -> bool:
        # Anthropic doesn't have a simple health endpoint
        return True

    async def complete(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        client = await self._get_client()

        # Convert messages to Anthropic format
        system_prompt = ""
        user_messages = []
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                user_messages.append({"role": msg.role, "content": msg.content})

        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system_prompt,
            "messages": user_messages,
        }

        try:
            client = await self._get_client()
            response = await client.post(
                "/v1/messages",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()

            content = data["content"][0]["text"]
            return LLMResponse(
                content=content,
                model=self.model,
                finish_reason=data.get("stop_reason"),
            )
        except Exception as e:
            logger.error(f"Anthropic completion failed: {e}")
            raise

    async def complete_structured(
        self,
        messages: List[LLMMessage],
        response_schema: Dict[str, Any],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        # Add schema instruction to system prompt
        schema_instruction = f"\n\nRespond with valid JSON matching this schema:\n{json.dumps(response_schema, indent=2)}"

        enhanced_messages = []
        for msg in messages:
            if msg.role == "system":
                enhanced_messages.append(LLMMessage(
                    role="system",
                    content=msg.content + schema_instruction
                ))
            else:
                enhanced_messages.append(msg)

        response = await self.complete(
            messages=enhanced_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return extract_json_object(response.content)

    async def health_check(self) -> bool:
        return True


class MockLLMClient(LLMClient):
    """Mock LLM client for testing without external dependencies."""

    def __init__(self):
        self.responses: Dict[str, Any] = {}

    def set_response(self, prompt_key: str, response: Dict[str, Any]):
        self.responses[prompt_key] = response

    def is_available(self) -> bool:
        """Check if the mock client is available (always True for mock)."""
        return True

    async def health_check(self) -> bool:
        return True

    async def complete(
        self,
        messages: Union[List[LLMMessage], str],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """Synchronous completion for testing."""
        # Handle both string and list of messages
        if isinstance(messages, str):
            key = messages
        else:
            key = messages[-1].content if messages else "default"
        response = self.responses.get(key, {
            "circuit_type": "ldo_regulator",
            "description": "Mock response",
            "input_voltage": 5.0,
            "output_voltage": 3.3,
            "current": 0.5,
        })
        return LLMResponse(content=json.dumps(response))

    async def complete_structured(
        self,
        messages: List[LLMMessage],
        response_schema: Dict[str, Any],
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        key = messages[-1].content if messages else "default"
        # Try to match based on circuit type in the prompt
        prompt_text = key.lower()
        
        # Check for explicit circuit type keywords in prompt - order matters!
        # Check more specific terms first
        if "buck" in prompt_text and ("converter" in prompt_text or "step-down" in prompt_text):
            return self.responses.get("buck", {
                "circuit_type": "buck_converter",
                "description": "Mock buck converter circuit",
                "input_voltage": 12.0,
                "output_voltage": 5.0,
                "output_current": 3.0,
            })
        elif "boost" in prompt_text and ("converter" in prompt_text or "step-up" in prompt_text):
            return self.responses.get("boost", {
                "circuit_type": "boost_converter",
                "description": "Mock boost converter circuit",
                "input_voltage": 3.3,
                "output_voltage": 5.0,
                "output_current": 1.0,
            })
        elif "ldo" in prompt_text or "linear regulator" in prompt_text:
            return self.responses.get("ldo", {
                "circuit_type": "ldo_regulator",
                "description": "Mock LDO regulator circuit",
                "input_voltage": 5.0,
                "output_voltage": 3.3,
                "output_current": 0.5,
            })
        elif "led" in prompt_text:
            return self.responses.get("led", {
                "circuit_type": "led_driver",
                "description": "Mock LED driver circuit",
                "input_voltage": 5.0,
                "output_voltage": None,
                "output_current": 0.02,
            })
        
        # Try to match based on response keys
        for response_key, response_value in self.responses.items():
            if response_key != "default" and response_key in key:
                return response_value
        
        return self.responses.get("default", {
            "circuit_type": "ldo_regulator",
            "description": "Mock LDO regulator circuit",
            "input_voltage": 5.0,
            "output_voltage": 3.3,
            "output_current": 0.5,
        })

    async def health_check(self) -> bool:
        return True


def create_llm_client(
    provider: Union[LLMProvider, str] = LLMProvider.MOCK,
    **kwargs,
) -> LLMClient:
    """Factory function to create LLM client."""
    # Convert string to enum if needed
    if isinstance(provider, str):
        try:
            provider = LLMProvider(provider.lower())
        except ValueError:
            raise ValueError(f"Unknown provider: {provider}")

    if provider == LLMProvider.OLLAMA:
        return OllamaClient(**kwargs)
    elif provider == LLMProvider.OPENAI:
        return OpenAIClient(**kwargs)
    elif provider == LLMProvider.ANTHROPIC:
        return AnthropicClient(**kwargs)
    elif provider == LLMProvider.MOCK:
        return MockLLMClient()
    else:
        raise ValueError(f"Unknown provider: {provider}")