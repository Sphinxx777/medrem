from fastapi import APIRouter

from .prescription import router as prescription_router

api_router = APIRouter()
api_router.include_router(prescription_router)
