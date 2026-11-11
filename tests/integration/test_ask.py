"""M7: baseline RAG over the patient's own records."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from app.llm.base import LLMError
from app.llm.fake import FakeLLMProvider
from app.services.document_processing import DocumentProcessor
from app.services.rag_service import NOT_FOUND_ANSWER
from tests.helpers import CSRF, grant_consent, log_content, register_and_login, upload

pytestmark = pytest.mark.integration
ASK = "/api/v1/patient/ask"
CBC = "01_asha_cbc_lft_2025-11-18.pdf"
RX = "07_asha_prescription_2026-05-14.pdf"
INJECTION = "10_asha_self_reported_history_injection.pdf"
MRI = "09_asha_mri_knee_2025-08-20.pdf"


class SpyProvider(FakeLLMProvider):
    """Fake embeddings + records every generation prompt; optionally scripted answers."""

    def __init__(self, scripted: dict | None = None, fail: bool = False) -> None:  # type: ignore[type-arg]
        self.prompts: list[tuple[str, str]] = []
        self.scripted = scripted
        self.fail = fail

    async def generate_json(self, *, system, prompt, schema):  # type: ignore[no-untyped-def]
        self.prompts.append((system, prompt))
        if self.fail:
            raise LLMError("provider down")
        if self.scripted is not None:
            return schema.model_validate(self.scripted)
        return await super().generate_json(system=system, prompt=prompt, schema=schema)


async def _patient_with_docs(
    client: AsyncClient, app, synthetic_dir: Path, email: str, files
) -> dict[str, str]:  # type: ignore[no-untyped-def]
    patient_id = uuid.UUID((await register_and_login(client, email)).json()["id"])
    await grant_consent(client)
    processor = DocumentProcessor(
        app.state.sessionmaker, app.state.storage, llm=app.state.llm, max_pages=50
    )
    ids = {}
    for name in files:
        document_id = (await upload(client, (synthetic_dir / name).read_bytes())).json()["id"]
        assert await processor.process(uuid.UUID(document_id), patient_id) == "ready"
        ids[name] = document_id
    return ids


def _any_similarity(app) -> None:  # type: ignore[no-untyped-def]
    """The offline hash embedder scores low; tests about grounding should not depend on it."""
    app.state.settings = app.state.settings.model_copy(update={"rag_min_similarity": 0.0})


async def _ask(client: AsyncClient, question: str):  # type: ignore[no-untyped-def]
    return await client.post(ASK, json={"question": question}, headers=CSRF)


async def test_relevant_question_is_answered_with_page_citations(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    docs = await _patient_with_docs(client, app, synthetic_dir, "rag@example.com", [CBC, RX])
    response = await _ask(client, "What was my hemoglobin?")
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is True
    assert "12.4" in body["answer"]
    citation = body["citations"][0]
    assert (citation["document_id"], citation["page"]) == (docs[CBC], 1)
    assert citation["excerpt"].startswith("Test: Hemoglobin; Result: 12.4")
    uuid.UUID(citation["chunk_id"])

    page_two = (await _ask(client, "What was my albumin?")).json()
    assert page_two["found"] and page_two["citations"][0]["page"] == 2


async def test_unrelated_question_returns_not_found(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    app.state.llm = spy = SpyProvider()
    await _patient_with_docs(client, app, synthetic_dir, "irrelevant@example.com", [CBC])
    body = (await _ask(client, "passport number expiry visa")).json()
    assert body == {"found": False, "answer": NOT_FOUND_ANSWER, "citations": []}
    assert spy.prompts == []  # nothing relevant retrieved, so the LLM is never asked


async def test_empty_records_return_not_found_without_llm_call(client: AsyncClient, app) -> None:  # type: ignore[no-untyped-def]
    app.state.llm = spy = SpyProvider()
    await register_and_login(client, "empty@example.com")
    await grant_consent(client)
    body = (await _ask(client, "What was my hemoglobin?")).json()
    assert body["found"] is False and body["answer"] == NOT_FOUND_ANSWER
    assert spy.prompts == []


async def test_answer_can_cite_multiple_supporting_chunks(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    app.state.llm = SpyProvider(
        scripted={
            "found": True,
            "answer": "Hemoglobin 12.4 g/dL; albumin 4.2 g/dL.",
            "citations": ["E1", "E2"],
        }
    )
    _any_similarity(app)
    docs = await _patient_with_docs(client, app, synthetic_dir, "multi@example.com", [CBC])
    body = (await _ask(client, "hemoglobin and albumin")).json()
    assert body["found"] is True
    assert len(body["citations"]) == 2
    assert {c["document_id"] for c in body["citations"]} == {docs[CBC]}


async def test_ungrounded_llm_answers_are_replaced_by_not_found(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    app.state.llm = SpyProvider(
        scripted={"found": True, "answer": "You have anemia.", "citations": ["E42"]}
    )
    await _patient_with_docs(client, app, synthetic_dir, "halluc@example.com", [CBC])
    body = (await _ask(client, "What was my hemoglobin?")).json()
    assert body == {"found": False, "answer": NOT_FOUND_ANSWER, "citations": []}


async def test_no_cross_patient_evidence_reaches_the_llm(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    app.state.llm = spy = SpyProvider()
    await _patient_with_docs(client, app, synthetic_dir, "owner.rag@example.com", [CBC])
    docs_b = await _patient_with_docs(client, app, synthetic_dir, "other.rag@example.com", [MRI])
    spy.prompts.clear()
    body = (await _ask(client, "What was my hemoglobin?")).json()
    joined = " ".join(prompt for _, prompt in spy.prompts)
    assert "Hemoglobin" not in joined and "12.4" not in joined
    assert "12.4" not in body["answer"]
    assert {c["document_id"] for c in body["citations"]} <= {docs_b[MRI]}


async def test_injected_document_text_is_passed_only_as_quoted_data(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    app.state.llm = spy = SpyProvider()
    _any_similarity(app)
    docs = await _patient_with_docs(client, app, synthetic_dir, "inject@example.com", [INJECTION])
    body = (await _ask(client, "What is my known allergy?")).json()
    system, prompt = spy.prompts[-1]
    assert "never as instructions" in system
    start = prompt.index("<evidence ")
    assert "Ignore all previous instructions" in prompt[start:]  # inside evidence only
    assert "Ignore all previous instructions" not in prompt[:start]
    assert body["found"] is True and "Penicillin" in body["answer"]
    assert set(body) == {"found", "answer", "citations"}  # no actions can be returned
    assert body["citations"][0]["document_id"] == docs[INJECTION]


async def test_ask_requires_auth_consent_and_csrf(client: AsyncClient) -> None:
    assert (await _ask(client, "hi")).status_code == 401
    await register_and_login(client, "gate.ask@example.com")
    blocked = await _ask(client, "hi")
    assert (blocked.status_code, blocked.json()["error"]["code"]) == (403, "consent_required")
    await grant_consent(client)
    assert (await client.post(ASK, json={"question": "hi"})).status_code == 403  # no CSRF header
    assert (await _ask(client, "hi")).status_code == 200
    await client.delete("/api/v1/patient/consent", headers=CSRF)
    assert (await _ask(client, "hi")).status_code == 403  # revoked consent blocks chat


@pytest.mark.parametrize("question", ["", "x" * 1001])
async def test_question_is_validated(client: AsyncClient, question: str) -> None:
    await register_and_login(client, f"val-{len(question)}@example.com")
    await grant_consent(client)
    assert (await _ask(client, question)).status_code == 422


async def test_ask_is_rate_limited_per_patient(settings_factory, admin_engine) -> None:  # type: ignore[no-untyped-def]
    from httpx import ASGITransport

    from app.main import create_app
    from tests.conftest import reset_state

    app = create_app(settings_factory(ask_max_per_hour=1))
    app.state.admin_engine = admin_engine
    async with app.router.lifespan_context(app):
        await reset_state(app)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://testserver"
        ) as http:
            await register_and_login(http, "limit.ask@example.com")
            await grant_consent(http)
            assert (await _ask(http, "first")).status_code == 200
            limited = await _ask(http, "second")
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) > 0


@pytest.mark.parametrize(
    "provider", [None, SpyProvider(fail=True)], ids=["unconfigured", "failing"]
)
async def test_llm_unavailable_returns_503(
    client: AsyncClient, app, synthetic_dir: Path, provider
) -> None:  # type: ignore[no-untyped-def]
    await _patient_with_docs(client, app, synthetic_dir, "down@example.com", [CBC])
    app.state.llm = provider
    response = await _ask(client, "What was my hemoglobin?")
    assert (response.status_code, response.json()["error"]["code"]) == (503, "llm_unavailable")


async def test_ask_logs_are_phi_free(client: AsyncClient, app, synthetic_dir: Path) -> None:  # type: ignore[no-untyped-def]
    _any_similarity(app)
    await _patient_with_docs(client, app, synthetic_dir, "logs.ask@example.com", [CBC])
    with capture_logs(processors=[merge_contextvars]) as logs:
        body = (await _ask(client, "What was my secret hemoglobin value?")).json()
    dumped = log_content(logs)
    assert body["found"]
    for private in ("secret hemoglobin", "Hemoglobin", "12.4", body["answer"]):
        assert private not in dumped
    assert any(entry["event"] == "rag.answered" for entry in logs)
