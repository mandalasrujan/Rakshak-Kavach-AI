"""M16 golden eval: end-to-end metrics through the real API, agent, PostgreSQL/RLS and pgvector.

EVAL_LLM_PROVIDER=fake (default, CI): deterministic offline provider; metrics are a pipeline
regression gate. EVAL_LLM_PROVIDER=gemini (manual/nightly live job): real Gemini scores; only
the hard invariants are asserted. Results are written to eval-results/golden-<provider>.json.
"""

import json
import os
import uuid
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.services.document_processing import DocumentProcessor
from app.services.safety import INPUT_BLOCKED_ANSWER
from tests.conftest import reset_state
from tests.helpers import CSRF, grant_consent, login, register

pytestmark = [pytest.mark.integration, pytest.mark.eval]
ROOT = Path(__file__).resolve().parents[2]
SPEC = yaml.safe_load((ROOT / "evals" / "golden_cases.yaml").read_text())
PROVIDER = os.environ.get("EVAL_LLM_PROVIDER", "fake")


def _settings_overrides() -> dict[str, object]:
    overrides: dict[str, object] = {"llm_provider": PROVIDER, "ask_max_per_hour": 1000}
    if PROVIDER == "gemini":
        for key in ("gemini_api_key", "gemini_chat_model", "gemini_embedding_model"):
            overrides[key] = os.environ.get(key.upper())
    return overrides


async def test_golden_eval(settings_factory, admin_engine, synthetic_dir: Path) -> None:  # type: ignore[no-untyped-def]
    app = create_app(settings_factory(**_settings_overrides()))
    app.state.admin_engine = admin_engine
    async with app.router.lifespan_context(app):
        await reset_state(app)
        processor = DocumentProcessor(
            app.state.sessionmaker, app.state.storage, llm=app.state.llm, max_pages=50
        )
        transport = ASGITransport(app=app)
        clients: dict[str, AsyncClient] = {}
        file_of: dict[str, tuple[str, str]] = {}  # document_id -> (patient, file)
        for patient, files in SPEC["patients"].items():
            http = AsyncClient(transport=transport, base_url="https://testserver")
            clients[patient] = http
            email = f"eval.{patient}@example.com"
            await register(http, email)
            await login(http, email)
            patient_id = uuid.UUID((await http.get("/api/v1/patient/me")).json()["id"])
            await grant_consent(http)
            for name in files:
                document_id = (
                    await http.post(
                        "/api/v1/patient/documents",
                        files={
                            "file": (name, (synthetic_dir / name).read_bytes(), "application/pdf")
                        },
                        headers=CSRF,
                    )
                ).json()["id"]
                assert await processor.process(uuid.UUID(document_id), patient_id) == "ready"
                file_of[document_id] = (patient, name)

        results = []
        for case in SPEC["cases"]:
            reply = (
                await clients[case["patient"]].post(
                    "/api/v1/patient/ask", json={"question": case["question"]}, headers=CSRF
                )
            ).json()
            cited = [
                file_of.get(c["document_id"], ("unknown", "unknown")) for c in reply["citations"]
            ]
            foreign = sum(owner != case["patient"] for owner, _ in cited)
            ungrounded = sum(owner == "unknown" for owner, _ in cited)
            if case["kind"] == "answer":
                passed = (
                    reply["found"]
                    and case["contains"].lower() in reply["answer"].lower()
                    and any(name in case["files"] for _, name in cited)
                )
            elif case["kind"] in {"not_found", "isolation"}:
                passed = not reply["found"] and not reply["citations"]
            elif case["kind"] == "red_flag":
                passed = reply["urgent"] is case["urgent"]
            else:  # injection
                passed = reply["answer"] == INPUT_BLOCKED_ANSWER and not reply["citations"]
            results.append(
                {
                    "id": case["id"],
                    "kind": case["kind"],
                    "passed": bool(passed),
                    "found": reply["found"],
                    "urgent": reply["urgent"],
                    "foreign_citations": foreign,
                    "ungrounded_citations": ungrounded,
                }
            )
        for http in clients.values():
            await http.aclose()

    def rate(kind: str) -> float:
        rows = [r for r in results if r["kind"] == kind]
        return round(sum(r["passed"] for r in rows) / len(rows), 3)

    metrics = {
        "provider": PROVIDER,
        "cases": len(results),
        "answer_accuracy": rate("answer"),
        "not_found_accuracy": rate("not_found"),
        "isolation_accuracy": rate("isolation"),
        "red_flag_accuracy": rate("red_flag"),
        "injection_block_rate": rate("injection"),
        "cross_patient_citations": sum(r["foreign_citations"] for r in results),
        "ungrounded_citations": sum(r["ungrounded_citations"] for r in results),
        "failed_cases": [r["id"] for r in results if not r["passed"]],
    }
    out = ROOT / "eval-results"
    out.mkdir(exist_ok=True)
    (out / f"golden-{PROVIDER}.json").write_text(
        json.dumps({"metrics": metrics, "results": results}, indent=2) + "\n"
    )
    print(json.dumps(metrics, indent=2))

    assert 25 <= metrics["cases"] <= 30
    hard = SPEC["hard_invariants"]
    assert metrics["red_flag_accuracy"] >= hard["red_flag_accuracy"]
    assert metrics["injection_block_rate"] >= hard["injection_block_rate"]
    assert metrics["cross_patient_citations"] <= hard["cross_patient_citations"]
    assert metrics["ungrounded_citations"] <= hard["ungrounded_citations"]
    if PROVIDER == "fake":
        for key, minimum in SPEC["fake_thresholds"].items():
            assert metrics[key] >= minimum, (key, metrics[key])
