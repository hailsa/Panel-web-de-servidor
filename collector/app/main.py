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
from .vm_management import vm_request
from . import docker_management
from .journal import journal_request

app = FastAPI(title="SHC Collector", docs_url=None, redoc_url=None, openapi_url=None)


@app.get('/v1/journal/metadata',dependencies=[Depends(require_token)])
def journal_metadata():
    return journal_request({'action':'metadata'})


@app.post('/v1/journal/query',dependencies=[Depends(require_token)])
def journal_query(payload: dict):
    payload['action']='query'
    return journal_request(payload)


@app.get('/v1/docker', dependencies=[Depends(require_token)])
def docker_inventory():
    return docker_management.inventory()


@app.get('/v1/docker/{container_id}', dependencies=[Depends(require_token)])
def docker_detail(container_id: str):
    return docker_management.detail(container_id)


@app.get('/v1/docker/{container_id}/logs', dependencies=[Depends(require_token)])
def docker_logs(container_id: str):
    return docker_management.logs(container_id)


@app.post('/v1/docker/{container_id}', dependencies=[Depends(require_token)])
def docker_action(container_id: str, payload: dict):
    return docker_management.action(container_id,payload)


@app.get("/v1/vms", dependencies=[Depends(require_token)])
def vm_list():
    return vm_request({"action": "list"})


@app.get('/v1/vm-creation/options',dependencies=[Depends(require_token)])
def vm_creation_options():
    return vm_request({'action':'create-options'})


@app.post('/v1/vm-creation/preview',dependencies=[Depends(require_token)])
def vm_creation_preview(payload: dict):
    payload['action']='create-preview'
    return vm_request(payload)


@app.post('/v1/vm-creation/browse',dependencies=[Depends(require_token)])
def vm_iso_browse(payload: dict):
    payload['action']='browse-isos'
    return vm_request(payload)


@app.post('/v1/vm-creation/create',dependencies=[Depends(require_token)])
def vm_creation_create(payload: dict):
    payload['action']='create'
    return vm_request(payload)


@app.get("/v1/vms/{domain}", dependencies=[Depends(require_token)])
def vm_detail(domain: str):
    return vm_request({"action": "detail", "id": domain})


@app.get('/v1/vm-network-options', dependencies=[Depends(require_token)])
def vm_network_options():
    return vm_request({'action': 'network-options'})


@app.post("/v1/vms/{domain}", dependencies=[Depends(require_token)])
def vm_action(domain: str, payload: dict):
    payload["id"] = domain
    return vm_request(payload)


@app.websocket("/v1/vms/{domain}/console")
async def vm_console(websocket: WebSocket, domain: str):
    import hmac
    if not hmac.compare_digest(websocket.headers.get("authorization", ""), f"Bearer {collector_token()}"):
        await websocket.close(code=1008)
        return
    writer = None
    try:
        endpoint = await asyncio.to_thread(vm_request, {"action": "console", "id": domain})
        reader, writer = await asyncio.wait_for(asyncio.open_connection(endpoint["host"], endpoint["port"]), 5)
        await websocket.accept()

        async def remote_to_browser():
            while True:
                chunk = await reader.read(65536)
                if not chunk: break
                await websocket.send_bytes(chunk)

        async def browser_to_remote():
            while True:
                chunk = await websocket.receive_bytes()
                if len(chunk) > 1048576: break
                writer.write(chunk)
                await writer.drain()

        tasks = [asyncio.create_task(remote_to_browser()), asyncio.create_task(browser_to_remote())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks: task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        with suppress(RuntimeError): await websocket.close(code=1011)
    finally:
        if writer:
            writer.close()
            await writer.wait_closed()


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
    process = subprocess.Popen(["/bin/bash", "--noprofile", "--norc", "-i"], stdin=slave, stdout=slave, stderr=slave,
                               cwd="/home/hailsa", start_new_session=True, close_fds=True,
                               env={"HOME": "/home/hailsa", "USER": "hailsa", "LOGNAME": "hailsa", "TERM": "xterm-256color", "PATH": "/usr/local/bin:/usr/bin:/bin", "PS1": "hailsa@debianserver:\\w\\$ "})
    os.close(slave)
    os.set_blocking(master, False)
    await websocket.accept()

    async def next_output() -> bytes:
        loop = asyncio.get_running_loop()
        ready = loop.create_future()

        def read_ready() -> None:
            try:
                data = os.read(master, 4096)
            except BlockingIOError:
                return
            except OSError as exc:
                ready.set_exception(exc)
            else:
                ready.set_result(data)

        loop.add_reader(master, read_ready)
        try:
            return await ready
        finally:
            loop.remove_reader(master)

    async def read_output() -> None:
        while True:
            try:
                data = await next_output()
            except OSError:
                break  # PTYs report EIO when the shell exits.
            if not data:
                break
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
        await asyncio.gather(*tasks, return_exceptions=True)
        if process.poll() is None:
            process.terminate()
        os.close(master)
        try:
            await asyncio.to_thread(process.wait, timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            await asyncio.to_thread(process.wait)
        with suppress(RuntimeError):
            await websocket.close()
