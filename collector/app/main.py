"""SHC collector ASGI application."""

from __future__ import annotations

import subprocess
import time
import platform
from typing import Literal

import psutil
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel

from .auth import require_token
from .collectors.details import collect_hardware, collect_physical_disks, collect_services, collect_voltages
from .collectors.snapshot import collect_snapshot
from .collectors.users import collect_users

app = FastAPI(title="SHC Collector", docs_url=None, redoc_url=None, openapi_url=None)


class PowerRequest(BaseModel):
    action: Literal["reboot", "poweroff"]


def _run_power_action(action: str) -> None:
    time.sleep(1.5)
    subprocess.run(["sudo", "-n", "/usr/bin/systemctl", action], check=False, timeout=10)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/snapshot", dependencies=[Depends(require_token)])
def snapshot() -> dict:
    return collect_snapshot()


@app.get("/v1/users", dependencies=[Depends(require_token)])
def users() -> dict:
    return {
        "available": True,
        "users": collect_users(),
        "system": {
            "hostname": platform.node(),
            "uptime_seconds": max(0, int(time.time() - psutil.boot_time())),
        },
    }


@app.get("/v1/server-status", dependencies=[Depends(require_token)])
def server_status() -> dict:
    data = collect_snapshot()
    data["hardware"] = collect_hardware()
    data["physical_disks"] = collect_physical_disks()
    data["voltages"] = collect_voltages()
    data["services"] = collect_services()
    return data


@app.post("/v1/system/power", dependencies=[Depends(require_token)])
def power(request: PowerRequest, background_tasks: BackgroundTasks) -> dict[str, str]:
    if request.action not in {"reboot", "poweroff"}:
        raise HTTPException(status_code=400, detail="Acción no válida")
    background_tasks.add_task(_run_power_action, request.action)
    return {"status": "accepted", "action": request.action}
