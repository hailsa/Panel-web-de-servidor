"""SHC dashboard web application."""

from __future__ import annotations

import os
import asyncio
import hmac
import time
from collections import defaultdict
from contextlib import suppress
from pathlib import Path

import httpx
import websockets
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import auth

BASE_DIR = Path(__file__).resolve().parent
SOCKET_PATH = os.getenv("SHC_COLLECTOR_SOCKET", "/run/shc-monitor/collector.sock")
TOKEN_FILE = Path(os.getenv("SHC_COLLECTOR_TOKEN_FILE", "/run/secrets/collector_token"))
APP_VERSION = "v0.4.8"

app = FastAPI(title="SHC Monitor", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
_login_attempts: dict[str, list[float]] = defaultdict(list)


@app.on_event("startup")
def startup() -> None:
    auth.init_db()


@app.middleware("http")
async def require_login(request: Request, call_next):
    if request.url.path in {"/login", "/health"} or request.url.path.startswith("/static/"):
        return await call_next(request)
    username = auth.session_user(request.cookies.get("shc_session"))
    if not username:
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "Iniciá sesión"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    request.state.username = username
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.url.path != "/logout":
        origin = request.headers.get("origin")
        expected = f"https://{request.headers.get('host', '')}"
        if origin != expected:
            return JSONResponse({"detail": "Origen inválido"}, status_code=403)
    return await call_next(request)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if auth.session_user(request.cookies.get("shc_session")):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request=request, name="login.html", context={"version": APP_VERSION})


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    username = str(form.get("username", ""))[:64]
    password = str(form.get("password", ""))
    client = request.client.host if request.client else "unknown"
    _login_attempts[client] = [stamp for stamp in _login_attempts[client] if time.monotonic() - stamp < 300]
    if len(_login_attempts[client]) >= 5:
        return templates.TemplateResponse(request=request, name="login.html", context={"version": APP_VERSION, "error": "Demasiados intentos. Esperá cinco minutos."}, status_code=429)
    token = auth.authenticate(username, password)
    if not token:
        _login_attempts[client].append(time.monotonic())
        return templates.TemplateResponse(request=request, name="login.html", context={"version": APP_VERSION, "error": "Usuario o contraseña incorrectos"}, status_code=401)
    _login_attempts.pop(client, None)
    response = RedirectResponse("/", status_code=303)
    response.set_cookie("shc_session", token, max_age=auth.SESSION_SECONDS, secure=True, httponly=True, samesite="strict")
    return response


@app.post("/logout")
async def logout(request: Request):
    session_token = request.cookies.get("shc_session")
    form = await request.form()
    submitted = str(form.get("csrf_token", ""))
    expected = auth.logout_csrf_token(session_token)
    if not expected or not hmac.compare_digest(submitted, expected):
        return JSONResponse({"detail": "Solicitud de cierre de sesión inválida"}, status_code=403)
    auth.revoke(session_token)
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie("shc_session")
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def page_context(request: Request, active: str) -> dict[str, str]:
    return {
        "active": active,
        "version": APP_VERSION,
        "logout_csrf_token": auth.logout_csrf_token(request.cookies.get("shc_session")),
    }


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context=page_context(request, "dashboard"))


@app.get("/usuarios", response_class=HTMLResponse)
def users_page(request: Request):
    return templates.TemplateResponse(request=request, name="users.html", context=page_context(request, "users"))


@app.get("/estado-servidor", response_class=HTMLResponse)
def server_status_page(request: Request):
    return templates.TemplateResponse(request=request, name="server_status.html", context=page_context(request, "status"))


async def _collector_get(path: str) -> JSONResponse:
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        transport = httpx.AsyncHTTPTransport(uds=SOCKET_PATH)
        async with httpx.AsyncClient(transport=transport, base_url="http://collector", timeout=8) as client:
            response = await client.get(path, headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
            return JSONResponse(response.json())
    except Exception as exc:
        return JSONResponse(
            {"available": False, "reason": "Collector no disponible", "detail": type(exc).__name__},
            status_code=503,
        )


async def _collector_post(path: str, payload: dict) -> JSONResponse:
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        transport = httpx.AsyncHTTPTransport(uds=SOCKET_PATH)
        async with httpx.AsyncClient(transport=transport, base_url="http://collector", timeout=8) as client:
            response = await client.post(path, json=payload, headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
            return JSONResponse(response.json())
    except Exception as exc:
        return JSONResponse(
            {"accepted": False, "reason": "No se pudo ejecutar la acción", "detail": type(exc).__name__},
            status_code=503,
        )


@app.get("/api/snapshot")
async def snapshot() -> JSONResponse:
    return await _collector_get("/v1/snapshot")


@app.get("/api/users")
async def users() -> JSONResponse:
    return await _collector_get("/v1/users")


@app.get("/api/server-status")
async def server_status() -> JSONResponse:
    return await _collector_get("/v1/server-status")


@app.post("/api/system/power")
async def power(request: Request) -> JSONResponse:
    if request.headers.get("x-shc-action") != "confirm":
        return JSONResponse({"accepted": False, "reason": "Confirmación requerida"}, status_code=403)
    payload = await request.json()
    if payload.get("action") not in {"reboot", "poweroff"}:
        return JSONResponse({"accepted": False, "reason": "Acción no válida"}, status_code=400)
    return await _collector_post("/v1/system/power", payload)


@app.websocket("/ws/terminal")
async def terminal(websocket: WebSocket):
    if not auth.session_user(websocket.cookies.get("shc_session")):
        await websocket.close(code=1008)
        return
    origin = websocket.headers.get("origin")
    if origin != f"https://{websocket.headers.get('host', '')}":
        await websocket.close(code=1008)
        return
    token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    try:
        async with websockets.unix_connect(SOCKET_PATH, uri="ws://collector/v1/terminal", additional_headers={"Authorization": f"Bearer {token}"}) as collector:
            await websocket.accept()

            async def browser_to_collector():
                while True:
                    await collector.send(await websocket.receive_text())

            async def collector_to_browser():
                async for data in collector:
                    await websocket.send_text(data)

            tasks = [asyncio.create_task(browser_to_collector()), asyncio.create_task(collector_to_browser())]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        with suppress(RuntimeError):
            await websocket.close(code=1011)
