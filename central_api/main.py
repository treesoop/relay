from __future__ import annotations

from fastapi import FastAPI

from central_api.embedding import EmbeddingClient, build_embedder
from central_api.routers.auth_router import router as auth_router
from central_api.routers.reviews import router as reviews_router
from central_api.routers.skills import router as skills_router


def create_app(*, embedder: EmbeddingClient | None = None) -> FastAPI:
    app = FastAPI(title="Relay Central API", version="0.1.0")

    app.state.embedder = embedder or build_embedder()

    app.include_router(auth_router)
    app.include_router(skills_router)
    app.include_router(reviews_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
