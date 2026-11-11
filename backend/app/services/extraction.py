"""Table-aware text extraction from digital PDFs (no OCR).

Lab tables (a test-name column and a result column) become one `lab_row` chunk per row, so a
value is never split from its test name, unit or reference range. All other text, including
non-lab tables rendered row by row, becomes `narrative` chunks split per page with page
numbers kept. CPU-bound: call through asyncio.to_thread.
"""

from dataclasses import dataclass

import pymupdf
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.models.chunk import LAB_ROW, NARRATIVE
from app.services.pdf_validation import PdfRejectedError, open_pdf

pymupdf.no_recommend_layout()  # keep stdout clean for JSON logs

NARRATIVE_CHUNK_SIZE = 1000
NARRATIVE_CHUNK_OVERLAP = 150
_TEST_HEADERS = frozenset({"test", "test name", "investigation", "parameter", "analyte"})
_RESULT_HEADERS = frozenset({"result", "results", "value", "observed value"})
_TEXT_BLOCK = 0

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=NARRATIVE_CHUNK_SIZE, chunk_overlap=NARRATIVE_CHUNK_OVERLAP
)


@dataclass(frozen=True)
class ExtractedChunk:
    page: int  # 1-based
    kind: str
    text: str
    # Lab rows only: (header, cell) pairs exactly as extracted, for deterministic parsing (M8).
    cells: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ExtractionResult:
    pages: int
    chunks: list[ExtractedChunk]


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _is_lab_table(header: list[str]) -> bool:
    names = {name.lower() for name in header}
    return bool(names & _TEST_HEADERS) and bool(names & _RESULT_HEADERS)


def _row_text(header: list[str], row: list[str]) -> str:
    return "; ".join(f"{name}: {value}" for name, value in zip(header, row, strict=False) if value)


def _extract_page(page: pymupdf.Page, page_number: int) -> list[ExtractedChunk]:
    lab_rows: list[ExtractedChunk] = []
    parts: list[tuple[float, str]] = []  # (y position, text) to keep reading order
    table_rects: list[pymupdf.Rect] = []

    for table in page.find_tables().tables:
        header = [_clean(name) for name in table.header.names]
        rows = table.extract()
        if not table.header.external:
            rows = rows[1:]  # first extracted row is the header itself
        cleaned = [[_clean(cell) for cell in row] for row in rows]
        cleaned = [row for row in cleaned if any(row)]
        rect = pymupdf.Rect(table.bbox)
        table_rects.append(rect)
        if _is_lab_table(header):
            lab_rows.extend(
                ExtractedChunk(
                    page_number,
                    LAB_ROW,
                    _row_text(header, row),
                    tuple(zip(header, row, strict=False)),
                )
                for row in cleaned
            )
        elif cleaned:
            parts.append((rect.y0, "\n".join(_row_text(header, row) for row in cleaned)))

    for x0, y0, x1, y1, text, _number, block_type in page.get_text("blocks", sort=True):
        block = pymupdf.Rect(x0, y0, x1, y1)
        if block_type == _TEXT_BLOCK and not any(block.intersects(r) for r in table_rects):
            if text.strip():
                parts.append((y0, " ".join(text.split())))

    narrative = "\n".join(text for _, text in sorted(parts, key=lambda part: part[0]))
    narrative_chunks = [
        ExtractedChunk(page_number, NARRATIVE, piece) for piece in _splitter.split_text(narrative)
    ]
    return lab_rows + narrative_chunks


def extract_pdf(data: bytes, *, max_pages: int) -> ExtractionResult:
    document = open_pdf(data, max_pages=max_pages)
    try:
        chunks = [
            chunk
            for page_number, page in enumerate(document, start=1)
            for chunk in _extract_page(page, page_number)
        ]
        if not chunks:
            raise PdfRejectedError("no_text_layer")  # scanned/image-only PDFs need OCR (not v1)
        return ExtractionResult(pages=document.page_count, chunks=chunks)
    finally:
        document.close()
