from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.core.config import settings
from app.core.security import rate_limit
from app.db.database import init_db
from app.tools import builtin  # noqa: F401  (registers builtin tools)
from app.workers.scheduler import scheduler

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
log = logging.getLogger("orion")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    log.info("ORION %s starting (env=%s, db=%s)", settings.app_version, settings.environment,
             settings.database_url.split("://")[0])
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
        log.info("ORION shutdown complete")


app = FastAPI(
    title=settings.app_name,
    description="Local-first autonomous AI assistant: chat, memory, RAG, tools, automations and governance.",
    version=settings.app_version,
    lifespan=lifespan,
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_list,
    allow_origin_regex=r"https://.*\.e2b\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:  # pragma: no cover - safety net
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error", "error": str(exc)[:200]})
    response.headers["X-Process-Time-Ms"] = str(int((time.perf_counter() - started) * 1000))
    response.headers["X-Orion-Version"] = settings.app_version
    return response


app.include_router(router, dependencies=[Depends(rate_limit)])


@app.get("/", tags=["system"])
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "status": "/v1/system/status",
    }
