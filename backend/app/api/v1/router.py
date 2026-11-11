"""Aggregates all /api/v1 routers."""

from fastapi import APIRouter

from app.api.v1 import ask, auth, chats, consent, documents, labs, patient, snapshots

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(patient.router)
api_router.include_router(consent.router)
api_router.include_router(documents.router)
api_router.include_router(ask.router)
api_router.include_router(labs.router)
api_router.include_router(chats.router)
api_router.include_router(snapshots.router)
