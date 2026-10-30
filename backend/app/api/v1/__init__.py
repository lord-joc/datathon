from fastapi import APIRouter

from app.api.v1 import public, rankings, system

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(public.router)
api_router.include_router(rankings.router)
