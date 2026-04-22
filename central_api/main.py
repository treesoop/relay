from __future__ import annotations

import os

from fastapi import FastAPI, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from central_api.embedding import EmbeddingClient, build_embedder
from central_api.routers.auth_router import router as auth_router
from central_api.routers.reviews import router as reviews_router
from central_api.routers.skills import router as skills_router


def _key_for_rate_limit(request: Request) -> str:
    """Prefer agent_id for rate limiting; fall back to client IP if header absent."""
    agent = request.headers.get("X-Relay-Agent-Id")
    if agent:
        return f"agent:{agent}"
    return f"ip:{get_remote_address(request)}"


def create_app(*, embedder: EmbeddingClient | None = None) -> FastAPI:
    app = FastAPI(title="Relay Central API", version="0.2.0")

    app.state.embedder = embedder or build_embedder()

    # In tests we skip the middleware entirely so we don't have to juggle per-test counters.
    if os.environ.get("RELAY_DISABLE_RATE_LIMIT") != "1":
        limiter = Limiter(
            key_func=_key_for_rate_limit,
            default_limits=["100/minute"],
        )
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)

    app.include_router(auth_router)
    app.include_router(skills_router)
    app.include_router(reviews_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
