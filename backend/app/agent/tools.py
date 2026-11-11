"""The agent's only tools: patient-scoped, read-only, deterministic.

Routing is rule-based (no LLM function calling): a question about a test name or a trend adds
`get_labs`, a question about medicines adds `get_medications`, and `search_records` always
runs. The LLM never chooses or parameterises a tool, so injected text cannot trigger one.
"""

import re
import uuid
from typing import Literal, TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.llm.base import LLMProvider
from app.models.chunk import Chunk
from app.repositories.medication_repository import MedicationRepository
from app.repositories.vector_store import PgVectorStore
from app.services.lab_comparison import COMPARISON_NOTE, LabComparison, LabPoint
from app.services.lab_normalization import load_dictionary
from app.services.lab_service import LabService

ToolName = Literal["search_records", "get_labs", "get_medications"]
MAX_LAB_TESTS = 3
_TREND_WORDS = re.compile(
    r"\b(trend|worse|worsen\w*|better|improv\w*|compar\w*|chang\w*|previous|latest|over time|"
    r"going up|going down|increas\w*|decreas\w*|lab results?|blood tests?|test results?)\b",
    re.I,
)
_MEDICATION_WORDS = re.compile(
    r"\b(medicines?|medications?|meds|tablets?|pills?|drugs?|prescri\w*|dosage|dose|taking)\b",
    re.I,
)


class ToolCall(TypedDict):
    tool: ToolName
    test_code: str | None


class Source(TypedDict):
    document_id: str
    page: int
    chunk_id: str
    excerpt: str


class Evidence(TypedDict):
    id: str
    kind: str  # chunk | lab_trend | medication
    text: str
    sources: list[Source]


def find_test_codes(question: str) -> list[str]:
    """Canonical test codes named in the question (longest alias first, whole words only)."""
    text = f" {' '.join(re.findall(r'[a-z0-9]+', question.lower()))} "
    codes: list[str] = []
    aliases = sorted(load_dictionary().aliases.items(), key=lambda item: -len(item[0]))
    for alias, code in aliases:
        words = " ".join(re.findall(r"[a-z0-9]+", alias))
        if len(words) < 3:  # skip ambiguous short aliases such as "k", "na", "hb"
            continue
        needle = f" {words} "
        if needle in text:
            text = text.replace(needle, " ")
            if code not in codes:
                codes.append(code)
    return codes


def route(question: str) -> list[ToolCall]:
    calls: list[ToolCall] = []
    codes = find_test_codes(question)
    if codes:
        calls += [{"tool": "get_labs", "test_code": c} for c in codes[:MAX_LAB_TESTS]]
    elif _TREND_WORDS.search(question):
        calls.append({"tool": "get_labs", "test_code": None})
    if _MEDICATION_WORDS.search(question):
        calls.append({"tool": "get_medications", "test_code": None})
    calls.append({"tool": "search_records", "test_code": None})
    return calls


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:g}"


def _describe_point(label: str, point: LabPoint, unit: str) -> str:
    return (
        f"{label}: {point.raw_value} {point.raw_unit} on {point.effective_date or 'unknown date'}"
        f" (= {_fmt(point.canonical_value)} {unit}; reference range on that report "
        f"{_fmt(point.canonical_ref_low)} to {_fmt(point.canonical_ref_high)} {unit})"
    )


def render_trend(trend: LabComparison) -> str:
    """Deterministic text for a computed comparison. The LLM explains it; it never recomputes."""
    parts = [f"{trend.test_name} ({trend.test_code}), computed comparison"]
    if trend.latest:
        parts.append(_describe_point("latest", trend.latest, trend.canonical_unit))
    if trend.previous:
        parts.append(_describe_point("previous", trend.previous, trend.canonical_unit))
    if trend.change is not None:
        percent = "" if trend.percent_change is None else f" ({trend.percent_change:+g}%)"
        parts.append(f"change: {trend.change:+g} {trend.canonical_unit}{percent}")
    if trend.direction:
        parts.append(f"direction: {trend.direction}")
    parts.append(f"status: {trend.status} ({trend.reason.replace('_', ' ')})")
    parts.append(COMPARISON_NOTE)
    return "; ".join(parts)


class AgentTools:
    def __init__(
        self,
        session: AsyncSession,
        patient_id: uuid.UUID,
        *,
        llm: LLMProvider,
        settings: Settings,
    ) -> None:
        self._session = session
        self._patient_id = patient_id
        self._llm = llm
        self._settings = settings

    async def _chunk_texts(self, chunk_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        result = await self._session.execute(
            select(Chunk.id, Chunk.text).where(
                Chunk.patient_id == self._patient_id, Chunk.id.in_(chunk_ids)
            )
        )
        return {chunk_id: text for chunk_id, text in result}

    async def search_records(self, question: str) -> list[tuple[str, str, list[Source]]]:
        query = await self._llm.embed_query(question)
        hits = await PgVectorStore(self._session, self._patient_id).search(
            query,
            embedding_model=self._llm.embedding_model,
            limit=self._settings.rag_top_k,
            min_similarity=self._settings.rag_min_similarity,
        )
        return [
            (
                "chunk",
                hit.text,
                [
                    {
                        "document_id": str(hit.document_id),
                        "page": hit.page,
                        "chunk_id": str(hit.chunk_id),
                        "excerpt": hit.text,
                    }
                ],
            )
            for hit in hits
        ]

    async def get_labs(self, test_code: str | None) -> list[tuple[str, str, list[Source]]]:
        trends = (await LabService(self._session, self._patient_id).trends(test_code=test_code))[
            :10
        ]
        points = [p for t in trends for p in (t.latest, t.previous) if p is not None]
        texts = await self._chunk_texts([p.chunk_id for p in points])
        items = []
        for trend in trends:
            sources: list[Source] = [
                {
                    "document_id": str(p.document_id),
                    "page": p.page,
                    "chunk_id": str(p.chunk_id),
                    "excerpt": texts.get(p.chunk_id, ""),
                }
                for p in (trend.latest, trend.previous)
                if p is not None
            ]
            if sources:
                items.append(("lab_trend", render_trend(trend), sources))
        return items

    async def get_medications(self) -> list[tuple[str, str, list[Source]]]:
        medications = await MedicationRepository(self._session, self._patient_id).list(limit=20)
        texts = await self._chunk_texts([m.chunk_id for m in medications])
        return [
            (
                "medication",
                f"Medication: {m.name}; dose: {m.dose or 'not stated'}; frequency: "
                f"{m.frequency or 'not stated'}; duration: {m.duration or 'not stated'}; "
                f"prescription dated {m.start_date or 'unknown'}",
                [
                    {
                        "document_id": str(m.document_id),
                        "page": m.page,
                        "chunk_id": str(m.chunk_id),
                        "excerpt": texts.get(m.chunk_id, m.raw_text),
                    }
                ],
            )
            for m in medications
        ]

    async def run(self, calls: list[ToolCall], question: str) -> list[Evidence]:
        evidence: list[Evidence] = []
        seen: set[str] = set()
        for call in calls:
            if call["tool"] == "get_labs":
                items = await self.get_labs(call["test_code"])
            elif call["tool"] == "get_medications":
                items = await self.get_medications()
            else:
                items = await self.search_records(question)
            for kind, text, sources in items:
                if text in seen:
                    continue
                seen.add(text)
                evidence.append(
                    {"id": f"E{len(evidence) + 1}", "kind": kind, "text": text, "sources": sources}
                )
        return evidence
