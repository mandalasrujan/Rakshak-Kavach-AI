"""M7 eval: retrieval hit rate@k, plus RAG vs long-context answer accuracy.

Runs in memory on the synthetic records (no database). Usage:
    python scripts/eval_retrieval.py [--provider fake|gemini] [--k 6] [--answers]
Gemini mode reads LLM_PROVIDER/GEMINI_* settings from the environment or .env.
The offline `fake` provider measures the pipeline, not real embedding quality.
"""

import argparse
import asyncio
import json
import sys
import tempfile
import time
import uuid
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]

from app.core.config import LLMSettings  # noqa: E402
from app.llm.factory import create_llm_provider  # noqa: E402
from app.repositories.vector_store import RetrievedChunk  # noqa: E402
from app.services.extraction import extract_pdf  # noqa: E402
from app.services.rag_service import SYSTEM_PROMPT, RagAnswer, build_prompt, ground  # noqa: E402
from scripts.generate_synthetic_pdfs import _reports, generate  # noqa: E402


async def _index(
    provider, out_dir: Path
) -> dict[str, list[tuple[str, RetrievedChunk, list[float]]]]:  # type: ignore[no-untyped-def]
    index: dict[str, list[tuple[str, RetrievedChunk, list[float]]]] = {}
    for report in _reports():
        document_id = uuid.uuid4()
        chunks = extract_pdf((out_dir / report.filename).read_bytes(), max_pages=50).chunks
        vectors = await provider.embed_documents([c.text for c in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            retrieved = RetrievedChunk(
                uuid.uuid4(), document_id, chunk.page, chunk.kind, chunk.text, 0.0
            )
            index.setdefault(report.patient.key, []).append((report.filename, retrieved, vector))
    return index


async def _answer(
    provider, question: str, evidence: list[RetrievedChunk]
) -> tuple[str, float, int]:  # type: ignore[no-untyped-def]
    prompt, by_id = build_prompt(question, evidence)
    started = time.perf_counter()
    raw = await provider.generate_json(system=SYSTEM_PROMPT, prompt=prompt, schema=RagAnswer)
    return ground(raw, by_id).answer, (time.perf_counter() - started) * 1000, len(prompt)


async def run(provider_name: str, k: int, answers: bool) -> dict[str, object]:
    settings = LLMSettings(llm_provider=provider_name)  # type: ignore[call-arg]
    provider = create_llm_provider(settings)
    questions = yaml.safe_load((ROOT / "evals" / "retrieval_questions.yaml").read_text())[
        "questions"
    ]
    with tempfile.TemporaryDirectory() as tmp:
        generate(Path(tmp))
        index = await _index(provider, Path(tmp))
    hits = 0
    stats = {"rag": [0, 0.0, 0], "long_context": [0, 0.0, 0]}  # correct, latency, prompt chars
    for item in questions:
        query = await provider.embed_query(item["question"])
        ranked = sorted(
            index[item["patient"]],
            key=lambda entry: -sum(a * b for a, b in zip(query, entry[2], strict=True)),
        )
        top = ranked[:k]
        hits += any(
            f == item["file"] and c.page == item["page"] and item["contains"] in c.text
            for f, c, _ in top
        )
        if answers:
            modes = {"rag": [c for _, c, _ in top], "long_context": [c for _, c, _ in ranked]}
            for mode, evidence in modes.items():
                text, latency, chars = await _answer(provider, item["question"], evidence)
                stats[mode][0] += item["answer"].lower() in text.lower()
                stats[mode][1] += latency
                stats[mode][2] += chars
    await provider.aclose()
    total = len(questions)
    result: dict[str, object] = {
        "provider": provider_name,
        "embedding_model": provider.embedding_model,
        "k": k,
        "questions": total,
        "retrieval_hit_rate": round(hits / total, 3),
    }
    if answers:
        for mode, (correct, latency, chars) in stats.items():
            result[f"{mode}_answer_accuracy"] = round(correct / total, 3)
            result[f"{mode}_avg_latency_ms"] = round(latency / total, 1)
            result[f"{mode}_avg_prompt_chars"] = round(chars / total)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--provider", choices=["fake", "gemini"], default="fake")
    parser.add_argument("--k", type=int, default=6)
    parser.add_argument("--answers", action="store_true", help="also compare RAG vs long context")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.provider, args.k, args.answers)), indent=2))


if __name__ == "__main__":
    main()
