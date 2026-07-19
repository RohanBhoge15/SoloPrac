# SoloPrac Backend Routers

from fastapi import APIRouter
from app.routers import health, auth, patients, agent, images, evaluation

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(patients.router, prefix="/patients", tags=["patients"])
api_router.include_router(agent.router, tags=["agent"])
api_router.include_router(images.router, tags=["images"])
api_router.include_router(evaluation.router, tags=["evaluation"])
