"""SHC collector ASGI application."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from .auth import require_token
from .collectors.snapshot import collect_snapshot

app = FastAPI(title="SHC Collector", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/snapshot", dependencies=[Depends(require_token)])
def snapshot() -> dict:
    return collect_snapshot()

