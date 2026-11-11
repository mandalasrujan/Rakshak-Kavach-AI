"""Ask a single question about your own records (Medical History Agent, no stored chat)."""

from fastapi import APIRouter, Depends

from app.agent.service import AgentService
from app.api.deps import (
    enforce_same_site_request,
    get_agent_service,
    get_current_patient,
    require_consent,
)
from app.core.errors import ErrorResponse
from app.schemas.ask import AskRequest, AskResponse

router = APIRouter(
    prefix="/patient/ask",
    tags=["ask"],
    dependencies=[Depends(enforce_same_site_request), Depends(get_current_patient)],
    responses={
        401: {"model": ErrorResponse, "description": "Not authenticated"},
        403: {"model": ErrorResponse, "description": "CSRF rejected or consent required"},
        429: {"model": ErrorResponse},
        503: {"model": ErrorResponse, "description": "LLM provider unavailable"},
    },
)


@router.post(
    "",
    response_model=AskResponse,
    summary="Answer a question from your own records",
    description=(
        "Answers only from your uploaded records, with page-level citations. When the records "
        "do not contain the answer, `found` is false and a fixed not-found message is returned."
    ),
    dependencies=[Depends(require_consent)],
)
async def ask(body: AskRequest, service: AgentService = Depends(get_agent_service)) -> AskResponse:
    return AskResponse.model_validate(await service.ask(body.question))
