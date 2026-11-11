"""M6: provider boundary -- deterministic fake embeddings and the Gemini REST adapter."""

import json

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from app.core.config import EMBEDDING_DIMENSION, LLMSettings, Settings
from app.llm.base import LLMError, LLMNotConfiguredError
from app.llm.factory import create_llm_provider
from app.llm.fake import FakeLLMProvider
from app.llm.gemini import GeminiProvider
from tests.conftest import TEST_JWT_SECRET

KEY = "test-gemini-key-not-real"


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_fake_embeddings_are_deterministic_normalized_and_semantic() -> None:
    fake = FakeLLMProvider()
    a, b, c = await fake.embed_documents(
        ["Test: Hemoglobin; Result: 12.4", "Test: Hemoglobin; Result: 12.4", "CT chest impression"]
    )
    assert a == b
    assert len(a) == EMBEDDING_DIMENSION
    assert abs(sum(v * v for v in a) - 1) < 1e-9
    query = await fake.embed_query("what was my hemoglobin")
    assert _cosine(query, a) > _cosine(query, c)


class _Answer(BaseModel):
    found: bool
    answer: str
    citations: list[str]


def _gemini(handler) -> GeminiProvider:  # type: ignore[no-untyped-def]
    return GeminiProvider(
        api_key=KEY,
        chat_model="chat-model",
        embedding_model="embed-model",
        timeout_seconds=5,
        transport=httpx.MockTransport(handler),
    )


async def test_gemini_embedding_request_shape_batching_and_normalization() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = json.loads(request.content)
        vectors = [{"values": [3.0, 4.0] + [0.0] * (EMBEDDING_DIMENSION - 2)}] * len(
            body["requests"]
        )
        return httpx.Response(200, json={"embeddings": vectors})

    provider = _gemini(handler)
    vectors = await provider.embed_documents([f"chunk {i}" for i in range(150)])
    await provider.aclose()

    assert len(vectors) == 150
    assert vectors[0][:2] == [0.6, 0.8]  # re-normalized
    assert [len(json.loads(c.content)["requests"]) for c in calls] == [100, 50]
    first = calls[0]
    assert first.url.path.endswith("/models/embed-model:batchEmbedContents")
    assert first.headers["x-goog-api-key"] == KEY
    assert KEY not in str(first.url)  # key never in the URL (logs, proxies)
    request = json.loads(first.content)["requests"][0]
    assert request["taskType"] == "RETRIEVAL_DOCUMENT"
    assert request["outputDimensionality"] == EMBEDDING_DIMENSION


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(429, json={"error": "quota"}),
        httpx.Response(200, json={"embeddings": [{"values": [1.0, 2.0]}]}),
        httpx.Response(200, text="not json"),
    ],
    ids=["http-error", "wrong-dimension", "invalid-json"],
)
async def test_gemini_embedding_errors_raise_llm_error(response: httpx.Response) -> None:
    provider = _gemini(lambda request: response)
    with pytest.raises(LLMError) as excinfo:
        await provider.embed_query("q")
    await provider.aclose()
    assert KEY not in str(excinfo.value)


async def test_gemini_generate_json_validates_schema() -> None:
    payload = {"found": True, "answer": "x", "citations": ["E1"]}

    def ok(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["generationConfig"]["temperature"] == 0
        assert body["systemInstruction"]["parts"][0]["text"] == "system"
        text = json.dumps(payload)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})

    provider = _gemini(ok)
    assert await provider.generate_json(system="system", prompt="p", schema=_Answer) == _Answer(
        **payload
    )
    await provider.aclose()

    bad = _gemini(
        lambda r: httpx.Response(
            200, json={"candidates": [{"content": {"parts": [{"text": '{"oops": 1}'}]}}]}
        )
    )
    with pytest.raises(LLMError):
        await bad.generate_json(system="s", prompt="p", schema=_Answer)
    await bad.aclose()


def test_factory_requires_key_and_models_and_ignores_placeholders() -> None:
    with pytest.raises(LLMNotConfiguredError):
        create_llm_provider(LLMSettings(_env_file=None))  # type: ignore[call-arg]
    placeholders = LLMSettings(
        _env_file=None,
        gemini_api_key="<your-gemini-api-key>",
        gemini_chat_model="<gemini-chat-model-name>",
        gemini_embedding_model="<gemini-embedding-model-name>",
    )  # type: ignore[call-arg]
    assert placeholders.gemini_api_key is None
    with pytest.raises(LLMNotConfiguredError):
        create_llm_provider(placeholders)
    assert isinstance(
        create_llm_provider(LLMSettings(_env_file=None, llm_provider="fake")), FakeLLMProvider
    )  # type: ignore[call-arg]


def test_fake_provider_is_refused_in_production() -> None:
    with pytest.raises(ValidationError):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            app_env="production",
            llm_provider="fake",
            database_url="postgresql+asyncpg://u:p@h/db",
            redis_url="redis://h:6379/0",
            jwt_secret_key=TEST_JWT_SECRET,
            frontend_origin="https://x.example",
        )
