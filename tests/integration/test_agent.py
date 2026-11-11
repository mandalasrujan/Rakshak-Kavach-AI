"""M10: LangGraph Medical History Agent end to end."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.agent.graph import build_agent_graph
from app.agent.service import AgentService
from app.core.errors import ConsentRequiredError
from app.db.patient_context import set_patient_context
from app.llm.fake import FakeLLMProvider
from app.services.document_processing import DocumentProcessor
from tests.helpers import CSRF, grant_consent, register_and_login, upload

pytestmark = pytest.mark.integration
CHATS = "/api/v1/patient/chats"
HBA1C_FILES = ["03_asha_hba1c_2025-11-18.pdf", "04_asha_glycated_haemoglobin_2026-05-13.pdf"]
RX = "07_asha_prescription_2026-05-14.pdf"


class SpyProvider(FakeLLMProvider):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def generate_json(self, *, system, prompt, schema):  # type: ignore[no-untyped-def]
        self.prompts.append(prompt)
        return await super().generate_json(system=system, prompt=prompt, schema=schema)


async def _patient(
    client: AsyncClient, app, synthetic_dir: Path, email: str, files
) -> tuple[uuid.UUID, dict[str, str]]:  # type: ignore[no-untyped-def]
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
    return patient_id, ids


def test_graph_has_the_expected_nodes(app) -> None:  # type: ignore[no-untyped-def]
    graph = build_agent_graph(
        session=None, patient_id=uuid.uuid4(), llm=FakeLLMProvider(), settings=app.state.settings
    )  # type: ignore[arg-type]
    assert {"consent", "tools", "answer", "finalize"} <= set(graph.get_graph().nodes)


async def test_trend_question_uses_computed_comparison_with_both_sources(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    app.state.llm = spy = SpyProvider()
    _, docs = await _patient(client, app, synthetic_dir, "agent.trend@example.com", HBA1C_FILES)
    body = (
        await client.post(
            "/api/v1/patient/ask", json={"question": "Is my HbA1c getting worse?"}, headers=CSRF
        )
    ).json()
    assert body["found"] is True and "worsened" in body["answer"]
    assert {c["document_id"] for c in body["citations"]} == set(docs.values())
    assert all(c["page"] == 1 for c in body["citations"])
    assert "computed comparison" in spy.prompts[-1] and "change: +0.5 %" in spy.prompts[-1]


async def test_medication_question_uses_structured_medications(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    _, docs = await _patient(client, app, synthetic_dir, "agent.meds@example.com", [RX])
    body = (
        await client.post(
            "/api/v1/patient/ask",
            json={"question": "Which medication was prescribed?"},
            headers=CSRF,
        )
    ).json()
    assert body["found"] and ("Metformin" in body["answer"] or "Atorvastatin" in body["answer"])
    assert body["citations"][0]["document_id"] == docs[RX]


async def test_chat_persists_conversation_in_rls_checkpoints(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    app.state.llm = spy = SpyProvider()
    patient_id, docs = await _patient(
        client, app, synthetic_dir, "agent.chat@example.com", HBA1C_FILES
    )
    chat = (await client.post(CHATS, headers=CSRF)).json()
    first = await client.post(
        f"{CHATS}/{chat['id']}/messages", json={"question": "What was my HbA1c?"}, headers=CSRF
    )
    assert first.status_code == 200 and first.json()["chat_id"] == chat["id"]
    second = (
        await client.post(
            f"{CHATS}/{chat['id']}/messages",
            json={"question": "Is it getting worse?"},
            headers=CSRF,
        )
    ).json()
    # The follow-up has no test name; history is carried over and get_labs(all) still runs.
    # (Resolving "it" is the LLM's job; the offline fake answerer cannot, so `found` is not
    # asserted here.)
    assert '<turn role="user">What was my HbA1c?</turn>' in spy.prompts[-1]
    assert "computed comparison" in spy.prompts[-1]
    assert second["chat_id"] == chat["id"]

    history = (await client.get(f"{CHATS}/{chat['id']}/messages")).json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    assert history[0]["content"] == "What was my HbA1c?"
    assert [c["id"] for c in (await client.get(CHATS)).json()["items"]] == [chat["id"]]

    async with app.state.admin_engine.connect() as conn:
        owners = set(
            (await conn.execute(text("SELECT DISTINCT patient_id FROM chat_checkpoints"))).scalars()
        )
        cited = set(
            (await conn.execute(text("SELECT document_id FROM message_citations"))).scalars()
        )
    assert owners == {patient_id}
    assert {str(d) for d in cited} <= set(docs.values()) and cited
    async with app.state.sessionmaker() as session:  # RLS: no context, no checkpoints
        assert (
            await session.execute(text("SELECT count(*) FROM chat_checkpoints"))
        ).scalar_one() == 0


async def test_chats_are_patient_scoped(client: AsyncClient, app, synthetic_dir: Path) -> None:  # type: ignore[no-untyped-def]
    await _patient(client, app, synthetic_dir, "chat.owner@example.com", [])
    chat = (await client.post(CHATS, headers=CSRF)).json()
    await client.post(f"{CHATS}/{chat['id']}/messages", json={"question": "hello"}, headers=CSRF)
    await _patient(client, app, synthetic_dir, "chat.intruder@example.com", [])
    for response in (
        await client.get(f"{CHATS}/{chat['id']}/messages"),
        await client.post(f"{CHATS}/{chat['id']}/messages", json={"question": "hi"}, headers=CSRF),
        await client.delete(f"{CHATS}/{chat['id']}", headers=CSRF),
    ):
        assert response.status_code == 404
    assert (await client.get(CHATS)).json()["items"] == []


async def test_deleting_a_chat_removes_its_conversation(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    await _patient(client, app, synthetic_dir, "chat.delete@example.com", HBA1C_FILES)
    chat = (await client.post(CHATS, headers=CSRF)).json()
    await client.post(
        f"{CHATS}/{chat['id']}/messages", json={"question": "What was my HbA1c?"}, headers=CSRF
    )
    assert (await client.delete(f"{CHATS}/{chat['id']}", headers=CSRF)).status_code == 204
    assert (await client.get(f"{CHATS}/{chat['id']}/messages")).status_code == 404
    async with app.state.admin_engine.connect() as conn:
        for table in ("chats", "chat_checkpoints", "chat_checkpoint_writes", "message_citations"):
            assert (await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one() == 0  # noqa: S608
        assert (
            await conn.execute(text("SELECT count(*) FROM audit_log WHERE action = 'chat.deleted'"))
        ).scalar_one() == 1


async def test_consent_is_enforced_inside_the_graph(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    patient_id, _ = await _patient(
        client, app, synthetic_dir, "graph.consent@example.com", HBA1C_FILES
    )
    await client.delete("/api/v1/patient/consent", headers=CSRF)
    async with app.state.sessionmaker() as session:  # bypass the route-level dependency
        await set_patient_context(session, patient_id)
        service = AgentService(
            session,
            patient_id,
            llm=app.state.llm,
            redis=app.state.redis,
            settings=app.state.settings,
            sessionmaker=app.state.sessionmaker,
        )
        with pytest.raises(ConsentRequiredError):
            await service.ask("What was my HbA1c?")


async def test_chat_routes_require_consent_and_csrf(client: AsyncClient) -> None:
    await register_and_login(client, "chat.gate@example.com")
    assert (await client.post(CHATS, headers=CSRF)).status_code == 403  # no consent
    await grant_consent(client)
    assert (await client.post(CHATS)).status_code == 403  # no CSRF header
    assert (await client.post(CHATS, headers=CSRF)).status_code == 201
