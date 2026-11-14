"""Summary snapshots: generate (new version), list, preview, approve."""

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    enforce_same_site_request,
    get_current_patient,
    get_snapshot_service,
    require_consent,
)
from app.core.errors import ErrorResponse
from app.schemas.snapshot import SnapshotList, SnapshotRead
from app.services.snapshot_service import SnapshotService

router = APIRouter(
    prefix="/patient/snapshots",
    tags=["snapshots"],
    dependencies=[Depends(enforce_same_site_request), Depends(get_current_patient)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
    },
)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=SnapshotRead,
    summary="Generate a new summary snapshot version (draft until approved)",
    dependencies=[Depends(require_consent)],
)
async def generate_snapshot(
    service: SnapshotService = Depends(get_snapshot_service),
) -> SnapshotRead:
    return SnapshotRead.model_validate(await service.generate())


@router.get("", response_model=SnapshotList, summary="All snapshot versions (newest first)")
async def list_snapshots(service: SnapshotService = Depends(get_snapshot_service)) -> SnapshotList:
    return SnapshotList(items=[SnapshotRead.model_validate(s) for s in await service.list_all()])


@router.get("/{snapshot_id}", response_model=SnapshotRead, summary="Preview a snapshot")
async def get_snapshot(
    snapshot_id: uuid.UUID, service: SnapshotService = Depends(get_snapshot_service)
) -> SnapshotRead:
    return SnapshotRead.model_validate(await service.get(snapshot_id))


@router.post(
    "/{snapshot_id}/approve",
    response_model=SnapshotRead,
    summary="Approve a snapshot for sharing (it can never change afterwards)",
    dependencies=[Depends(require_consent)],
    responses={409: {"model": ErrorResponse}},
)
async def approve_snapshot(
    snapshot_id: uuid.UUID, service: SnapshotService = Depends(get_snapshot_service)
) -> SnapshotRead:
    return SnapshotRead.model_validate(await service.approve(snapshot_id))
