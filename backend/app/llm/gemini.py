"""Google Gemini over its REST API (httpx). The API key travels in a header, never in URLs or
logs; response bodies are never logged because they may echo patient text."""

from collections.abc import Sequence

import httpx
from pydantic import ValidationError

from app.core.config import EMBEDDING_DIMENSION
from app.llm.base import LLMError, SchemaT, l2_normalize

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/"
_BATCH_SIZE = 100


class GeminiProvider:
    embedding_dimension = EMBEDDING_DIMENSION

    def __init__(
        self,
        *,
        api_key: str,
        chat_model: str,
        embedding_model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.embedding_model = embedding_model
        self.chat_model = chat_model
        self._client = httpx.AsyncClient(
            base_url=GEMINI_BASE_URL,
            headers={"x-goog-api-key": api_key},
            timeout=timeout_seconds,
            transport=transport,
        )

    async def _post(self, path: str, body: dict[str, object]) -> dict[str, object]:
        try:
            response = await self._client.post(path, json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"gemini request failed: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise LLMError(f"gemini returned HTTP {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise LLMError("gemini returned invalid JSON") from exc

    async def _embed(self, texts: Sequence[str], task_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        model = f"models/{self.embedding_model}"
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start : start + _BATCH_SIZE]
            data = await self._post(
                f"{model}:batchEmbedContents",
                {
                    "requests": [
                        {
                            "model": model,
                            "content": {"parts": [{"text": text}]},
                            "taskType": task_type,
                            "outputDimensionality": EMBEDDING_DIMENSION,
                        }
                        for text in batch
                    ]
                },
            )
            try:
                values = [item["values"] for item in data["embeddings"]]  # type: ignore[index, union-attr]
            except (KeyError, TypeError) as exc:
                raise LLMError("unexpected embedding response") from exc
            if len(values) != len(batch) or any(len(v) != EMBEDDING_DIMENSION for v in values):
                raise LLMError("embedding count or dimension mismatch")
            # Truncated-dimension Gemini embeddings must be re-normalized for cosine search.
            vectors.extend(l2_normalize(v) for v in values)
        return vectors

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return await self._embed(texts, "RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text], "RETRIEVAL_QUERY"))[0]

    async def generate_json(self, *, system: str, prompt: str, schema: type[SchemaT]) -> SchemaT:
        data = await self._post(
            f"models/{self.chat_model}:generateContent",
            {
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
            },
        )
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]  # type: ignore[index]
            return schema.model_validate_json(text)
        except (KeyError, IndexError, TypeError, ValidationError) as exc:
            raise LLMError("response did not match the expected schema") from exc

    async def aclose(self) -> None:
        await self._client.aclose()
