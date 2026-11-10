"""Deterministic PDF checks. Runs in the worker so untrusted PDFs are never parsed by the API.

CPU-bound: call through asyncio.to_thread.
"""

import pymupdf

PDF_MAGIC = b"%PDF-"


class PdfRejectedError(Exception):
    """A permanent, non-retryable problem with the file. `reason` is stored on the document."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def open_pdf(data: bytes, *, max_pages: int) -> pymupdf.Document:
    """Open and validate a PDF; caller must close the returned document."""
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise PdfRejectedError("unreadable_pdf") from exc
    try:
        if document.needs_pass or document.is_encrypted:
            raise PdfRejectedError("encrypted_pdf")
        if document.page_count == 0:
            raise PdfRejectedError("unreadable_pdf")
        if document.page_count > max_pages:
            raise PdfRejectedError("too_many_pages")
    except PdfRejectedError:
        document.close()
        raise
    return document


def count_pages(data: bytes, *, max_pages: int) -> int:
    document = open_pdf(data, max_pages=max_pages)
    try:
        return document.page_count
    finally:
        document.close()
