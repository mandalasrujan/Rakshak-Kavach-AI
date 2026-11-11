"""The provider interface. Provider-specific code lives in gemini.py / fake.py only."""

from collections.abc import Sequence
from typing import Protocol, TypeVar

from pydantic import BaseModel

SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMError(Exception):
    """Transient or provider-side failure (network, HTTP status, malformed response)."""


class LLMNotConfiguredError(LLMError):
    """The provider cannot be used (missing key or model names). Not retryable."""


class LLMProvider(Protocol):
    chat_model: str
    embedding_model: str
    embedding_dimension: int

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...

    async def generate_json(self, *, system: str, prompt: str, schema: type[SchemaT]) -> SchemaT:
        """Generate a response that must validate against `schema` (raises LLMError)."""
        ...

    async def aclose(self) -> None: ...


def l2_normalize(vector: Sequence[float]) -> list[float]:
    norm = sum(v * v for v in vector) ** 0.5
    if norm == 0:
        raise LLMError("zero-length embedding")
    return [v / norm for v in vector]
