"""M6: non-owner app role, PostgreSQL RLS, transaction-scoped patient context, pgvector search."""

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from app.db.patient_context import set_patient_context
from app.repositories.vector_store import PgVectorStore
from app.services.document_processing import DocumentProcessor
from tests.conftest import TEST_APP_ROLE
from tests.helpers import grant_consent, log_content, register_and_login, upload

pytestmark = pytest.mark.integration
CBC = "01_asha_cbc_lft_2025-11-18.pdf"
RLS_TABLES = ("consent_records", "documents", "chunks", "audit_log")


def _processor(app, llm="default") -> DocumentProcessor:  # type: ignore[no-untyped-def]
    return DocumentProcessor(
        app.state.sessionmaker,
        app.state.storage,
        llm=app.state.llm if llm == "default" else llm,
        max_pages=50,
    )


async def _ready_patient(
    client: AsyncClient, app, data: bytes, email: str
) -> tuple[uuid.UUID, uuid.UUID]:  # type: ignore[no-untyped-def]
    patient_id = uuid.UUID((await register_and_login(client, email)).json()["id"])
    await grant_consent(client)
    document_id = uuid.UUID((await upload(client, data)).json()["id"])
    assert await _processor(app).process(document_id, patient_id) == "ready"
    return patient_id, document_id


@pytest.fixture
async def two_patients(client: AsyncClient, app, synthetic_dir: Path):  # type: ignore[no-untyped-def]
    data = (synthetic_dir / CBC).read_bytes()  # the same file for both patients
    a = await _ready_patient(client, app, data, "iso-a@example.com")
    b = await _ready_patient(client, app, data, "iso-b@example.com")
    return a, b


async def test_app_role_owns_nothing_and_cannot_bypass_rls(app) -> None:  # type: ignore[no-untyped-def]
    async with app.state.admin_engine.connect() as conn:
        role = (
            await conn.execute(
                text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :r"),
                {"r": TEST_APP_ROLE},
            )
        ).one()
        owned = (
            await conn.execute(
                text("SELECT count(*) FROM pg_tables WHERE tableowner = :r"), {"r": TEST_APP_ROLE}
            )
        ).scalar_one()
        rls = dict(
            (
                await conn.execute(
                    text("SELECT relname, relrowsecurity FROM pg_class WHERE relname = ANY(:t)"),
                    {"t": list(RLS_TABLES)},
                )
            ).all()
        )
    assert (role.rolsuper, role.rolbypassrls, owned) == (False, False, 0)
    assert rls == dict.fromkeys(RLS_TABLES, True)
    async with app.state.engine.connect() as conn:
        assert (await conn.execute(text("SELECT current_user"))).scalar_one() == TEST_APP_ROLE


async def test_missing_patient_context_sees_no_rows(app, two_patients) -> None:  # type: ignore[no-untyped-def]
    async with app.state.sessionmaker() as session:  # never bound to a patient
        counts = {
            t: (await session.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one()  # noqa: S608
            for t in RLS_TABLES
        }
    assert counts == dict.fromkeys(RLS_TABLES, 0)
    async with app.state.admin_engine.connect() as conn:  # the rows do exist
        assert (await conn.execute(text("SELECT count(*) FROM chunks"))).scalar_one() > 0


async def test_patient_context_is_transaction_scoped(app, two_patients) -> None:  # type: ignore[no-untyped-def]
    (patient_a, _), _ = two_patients
    async with app.state.engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.patient_id', :p, true)"), {"p": str(patient_a)}
            )
            inside = (await conn.execute(text("SELECT count(*) FROM chunks"))).scalar_one()
        async with conn.begin():  # SET LOCAL did not survive the commit
            after = (await conn.execute(text("SELECT count(*) FROM chunks"))).scalar_one()
    assert inside > 0
    assert after == 0


async def test_rls_hides_other_patients_even_without_a_where_clause(app, two_patients) -> None:  # type: ignore[no-untyped-def]
    (_, document_a), (patient_b, _) = two_patients
    async with app.state.sessionmaker() as session:
        await set_patient_context(session, patient_b)
        owners = set(
            (await session.execute(text("SELECT DISTINCT patient_id FROM chunks"))).scalars()
        )
        stolen = (
            await session.execute(
                text("SELECT count(*) FROM documents WHERE id = :d"), {"d": document_a}
            )
        ).scalar_one()
        await session.commit()  # context re-applied to the next transaction for a bound session
        again = set(
            (await session.execute(text("SELECT DISTINCT patient_id FROM documents"))).scalars()
        )
    assert owners == {patient_b}
    assert stolen == 0
    assert again == {patient_b}


async def test_rls_rejects_writes_for_another_patient(app, two_patients) -> None:  # type: ignore[no-untyped-def]
    (patient_a, _), (patient_b, _) = two_patients
    async with app.state.sessionmaker() as session:
        await set_patient_context(session, patient_a)
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO audit_log (id, patient_id, actor_type, action) "
                    "VALUES (:i, :p, 'system', 'forged')"
                ),
                {"i": uuid.uuid4(), "p": patient_b},
            )


async def test_app_role_cannot_truncate_or_rewrite_audit(app) -> None:  # type: ignore[no-untyped-def]
    for statement in ("TRUNCATE chunks", "UPDATE audit_log SET action = 'x'"):
        with pytest.raises(ProgrammingError, match="permission denied"):
            async with app.state.engine.begin() as conn:
                await conn.execute(text(statement))


async def test_session_cannot_be_rebound_to_another_patient(app) -> None:  # type: ignore[no-untyped-def]
    async with app.state.sessionmaker() as session:
        await set_patient_context(session, uuid.uuid4())
        with pytest.raises(RuntimeError):
            await set_patient_context(session, uuid.uuid4())


async def _search(app, bind_to: uuid.UUID, store_for: uuid.UUID, query: str):  # type: ignore[no-untyped-def]
    embedding = await app.state.llm.embed_query(query)
    async with app.state.sessionmaker() as session:
        await set_patient_context(session, bind_to)
        return await PgVectorStore(session, store_for).search(
            embedding, embedding_model=app.state.llm.embedding_model, limit=5, min_similarity=0.0
        )


async def test_vector_search_ranks_relevant_chunks_with_citation_metadata(
    app, two_patients
) -> None:  # type: ignore[no-untyped-def]
    (patient_a, document_a), _ = two_patients
    hits = await _search(app, patient_a, patient_a, "alt sgpt")
    top = hits[0]
    assert top.text.startswith("Test: ALT (SGPT)")
    assert (top.document_id, top.page, top.kind) == (document_a, 2, "lab_row")
    assert [h.similarity for h in hits] == sorted((h.similarity for h in hits), reverse=True)


async def test_vector_search_never_crosses_patients(app, two_patients) -> None:  # type: ignore[no-untyped-def]
    (patient_a, _), (patient_b, document_b) = two_patients
    own = await _search(app, patient_b, patient_b, "hemoglobin")
    assert own and {h.document_id for h in own} == {document_b}
    # Misuse: a store built for patient A on a session bound to patient B finds nothing.
    assert await _search(app, patient_b, patient_a, "hemoglobin") == []


async def test_embeddings_are_stored_and_replaced_on_reprocessing(app, two_patients) -> None:  # type: ignore[no-untyped-def]
    (patient_a, document_a), _ = two_patients

    async def snapshot():  # type: ignore[no-untyped-def]
        async with app.state.admin_engine.connect() as conn:
            return (
                await conn.execute(
                    text(
                        "SELECT id, embedding_model, vector_dims(embedding) AS dims FROM chunks "
                        "WHERE document_id = :d"
                    ),
                    {"d": document_a},
                )
            ).all()

    first = await snapshot()
    assert first and {(r.embedding_model, r.dims) for r in first} == {("fake-hash-768", 768)}
    async with app.state.admin_engine.begin() as conn:
        await conn.execute(
            text("UPDATE documents SET status = 'processing' WHERE id = :d"), {"d": document_a}
        )
    assert await _processor(app).process(document_a, patient_a) == "ready"
    second = await snapshot()
    assert len(second) == len(first)
    assert not {r.id for r in first} & {r.id for r in second}  # old rows gone, no stale vectors


async def test_missing_provider_fails_document_without_chunks(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    patient_id = uuid.UUID((await register_and_login(client, "nollm@example.com")).json()["id"])
    await grant_consent(client)
    document_id = uuid.UUID((await upload(client, (synthetic_dir / CBC).read_bytes())).json()["id"])
    assert await _processor(app, llm=None).process(document_id, patient_id) == "failed"
    body = (await client.get(f"/api/v1/patient/documents/{document_id}")).json()
    assert body["failure_reason"] == "embedding_unavailable"


async def test_processing_and_search_logs_are_phi_free(
    client: AsyncClient, app, synthetic_dir: Path
) -> None:  # type: ignore[no-untyped-def]
    with capture_logs(processors=[merge_contextvars]) as logs:
        patient_id, _ = await _ready_patient(
            client, app, (synthetic_dir / CBC).read_bytes(), "logs.m6@example.com"
        )
        await _search(app, patient_id, patient_id, "hemoglobin")
    dumped = log_content(logs)
    for secret in ("Hemoglobin", "Asha", "12.4", "logs.m6@example.com"):
        assert secret not in dumped
