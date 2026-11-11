"""Patient documents: upload (202, processed asynchronously), list, get status, delete."""

import uuid

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from app.api.deps import (
    enforce_same_site_request,
    get_app_settings,
    get_current_patient,
    get_document_deletion_service,
    get_document_service,
    require_consent,
)
from app.core.config import Settings
from app.core.errors import ErrorResponse, PayloadTooLargeError
from app.schemas.document import DocumentList, DocumentRead
from app.services.document_deletion import DocumentDeletionService
from app.services.document_service import DocumentService

router = APIRouter(
    prefix="/patient/documents",
    tags=["documents"],
    dependencies=[Depends(enforce_same_site_request), Depends(get_current_patient)],
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "CSRF rejected or consent required"},
    },
)

_READ_CHUNK = 1024 * 1024


async def _read_limited(file: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_READ_CHUNK):
        total += len(chunk)
        if total > max_bytes:
            raise PayloadTooLargeError()
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentRead,
    summary="Upload a digital PDF for processing",
    description=(
        "Returns 202 with a queued document. Re-uploading a file you already uploaded returns "
        "200 with the existing document (a previously failed one is queued again with 202)."
    ),
    dependencies=[Depends(require_consent)],
    responses={
        200: {"model": DocumentRead, "description": "Duplicate of an existing document"},
        413: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
    },
)
async def upload_document(
    response: Response,
    file: UploadFile = File(...),
    service: DocumentService = Depends(get_document_service),
    settings: Settings = Depends(get_app_settings),
) -> DocumentRead:
    data = await _read_limited(file, settings.max_upload_bytes)
    result = await service.upload(data)
    if not result.accepted:
        response.status_code = status.HTTP_200_OK
    return DocumentRead.model_validate(result.document)


@router.get("", response_model=DocumentList, summary="List your documents (newest first)")
async def list_documents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    service: DocumentService = Depends(get_document_service),
) -> DocumentList:
    items, total = await service.list(limit=limit, offset=offset)
    return DocumentList(
        items=[DocumentRead.model_validate(d) for d in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentRead,
    summary="Document status",
    responses={404: {"model": ErrorResponse}},
)
async def get_document(
    document_id: uuid.UUID,
    service: DocumentService = Depends(get_document_service),
) -> DocumentRead:
    return DocumentRead.model_validate(await service.get(document_id))


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document and everything derived from it",
    description=(
        "Deletes the stored file, its chunks and embeddings, lab results, medications, and any "
        "chats that cited it (with their stored conversation). Consent is not required to "
        "delete. A 503 means nothing was deleted and the request can be retried."
    ),
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
async def delete_document(
    document_id: uuid.UUID,
    service: DocumentDeletionService = Depends(get_document_deletion_service),
) -> Response:
    await service.delete(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
