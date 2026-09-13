"""SHC collector ASGI application."""

from __future__ import annotations

from fastapi import Depends, FastAPI

from .auth import require_token
from .collectors.details import collect_hardware, collect_physical_disks, collect_services, collect_voltages
from .collectors.snapshot import collect_snapshot
from .collectors.users import collect_users

app = FastAPI(title="SHC Collector", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/snapshot", dependencies=[Depends(require_token)])
def snapshot() -> dict:
    return collect_snapshot()


@app.get("/v1/users", dependencies=[Depends(require_token)])
def users() -> dict:
    return {"available": True, "users": collect_users()}


@app.get("/v1/server-status", dependencies=[Depends(require_token)])
def server_status() -> dict:
    data = collect_snapshot()
    data["hardware"] = collect_hardware()
    data["physical_disks"] = collect_physical_disks()
    data["voltages"] = collect_voltages()
    data["services"] = collect_services()
    return data
