"""Deterministic offline provider for tests and keyless local development.

Embeddings: hashed bag of words (no network). generate_json: an extractive stand-in for the
RAG answer only. Refused when APP_ENV=production (see config validators).
"""

import hashlib
import re
from collections.abc import Sequence

from app.core.config import EMBEDDING_DIMENSION
from app.llm.base import SchemaT, l2_normalize

FAKE_EMBEDDING_MODEL = f"fake-hash-{EMBEDDING_DIMENSION}"
_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by do does for from has have how i in is it my of on or "
    "the to was were what when which with you your me am did any".split()
)
_EVIDENCE = re.compile(r'<evidence id="(E\d+)"[^>]*>(.*?)</evidence>', re.DOTALL)
_QUESTION = re.compile(r"<question>(.*?)</question>", re.DOTALL)


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS]


class FakeLLMProvider:
    embedding_model = FAKE_EMBEDDING_MODEL
    embedding_dimension = EMBEDDING_DIMENSION

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * EMBEDDING_DIMENSION
        for token in tokens(text) or ["<empty>"]:
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSION
            vector[index] += 1.0
        if not any(vector):
            vector[0] = 1.0
        return l2_normalize(vector)

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    async def generate_json(self, *, system: str, prompt: str, schema: type[SchemaT]) -> SchemaT:
        question = _QUESTION.search(prompt)
        wanted = set(tokens(question.group(1))) if question else set()
        best: tuple[int, str, str] | None = None
        for evidence_id, text in _EVIDENCE.findall(prompt):
            overlap = len(wanted & set(tokens(text)))
            if overlap and (best is None or overlap > best[0]):
                best = (overlap, evidence_id, " ".join(text.split()))
        if best is None:
            return schema.model_validate({"found": False, "answer": "", "citations": []})
        return schema.model_validate(
            {"found": True, "answer": f"Your records show: {best[2]}", "citations": [best[1]]}
        )

    async def aclose(self) -> None:
        return None
