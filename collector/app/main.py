"""SHC collector ASGI application."""

from __future__ import annotations

import subprocess
import time
import platform
import os
import asyncio
import json
import pty
import fcntl
import termios
import struct
from contextlib import suppress
from typing import Literal

import psutil
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, WebSocket
from pydantic import BaseModel

from .auth import require_token
from .auth import collector_token
from .collectors.details import collect_hardware, collect_physical_disks, collect_services, collect_voltages
from .collectors.snapshot import collect_snapshot
from .collectors.users import collect_users

app = FastAPI(title="SHC Collector", docs_url=None, redoc_url=None, openapi_url=None)


class PowerRequest(BaseModel):
    action: Literal["reboot", "poweroff"]


def _run_power_action(action: str) -> None:
    time.sleep(1.5)
    result = subprocess.run(["sudo", "-n", "/usr/bin/systemctl", action], capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Power action failed")


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
    check = subprocess.run(["sudo", "-n", "-l", "/usr/bin/systemctl", request.action], capture_output=True, timeout=3)
    if check.returncode:
        raise HTTPException(status_code=503, detail="Permiso de energía no disponible")
    background_tasks.add_task(_run_power_action, request.action)
    return {"status": "accepted", "action": request.action}


@app.websocket("/v1/terminal")
async def terminal(websocket: WebSocket) -> None:
    import hmac
    if not hmac.compare_digest(websocket.headers.get("authorization", ""), f"Bearer {collector_token()}"):
        await websocket.close(code=1008)
        return
    master, slave = pty.openpty()
    process = subprocess.Popen(["/bin/bash", "--login"], stdin=slave, stdout=slave, stderr=slave,
                               cwd="/home/hailsa", start_new_session=True, close_fds=True,
                               env={"HOME": "/home/hailsa", "USER": "hailsa", "LOGNAME": "hailsa", "TERM": "xterm-256color", "PATH": "/usr/local/bin:/usr/bin:/bin"})
    os.close(slave)
    await websocket.accept()

    async def read_output() -> None:
        while process.poll() is None:
            data = await asyncio.to_thread(os.read, master, 4096)
            await websocket.send_text(data.decode("utf-8", errors="replace"))

    async def read_input() -> None:
        while True:
            message = json.loads(await websocket.receive_text())
            if message.get("type") == "input":
                os.write(master, str(message.get("data", "")).encode())
            elif message.get("type") == "resize":
                rows = max(10, min(100, int(message.get("rows", 24))))
                cols = max(30, min(300, int(message.get("cols", 80))))
                fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    tasks = [asyncio.create_task(read_output()), asyncio.create_task(read_input())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        if process.poll() is None:
            process.terminate()
        os.close(master)
        await asyncio.gather(*tasks, return_exceptions=True)
        with suppress(RuntimeError):
            await websocket.close()
