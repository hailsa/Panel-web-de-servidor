"""SHC dashboard web application."""

from __future__ import annotations

import os
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
SOCKET_PATH = os.getenv("SHC_COLLECTOR_SOCKET", "/run/shc-monitor/collector.sock")
TOKEN_FILE = Path(os.getenv("SHC_COLLECTOR_TOKEN_FILE", "/run/secrets/collector_token"))

app = FastAPI(title="SHC Monitor", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/api/snapshot")
async def snapshot() -> JSONResponse:
    try:
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        transport = httpx.AsyncHTTPTransport(uds=SOCKET_PATH)
        async with httpx.AsyncClient(transport=transport, base_url="http://collector", timeout=8) as client:
            response = await client.get("/v1/snapshot", headers={"Authorization": f"Bearer {token}"})
            response.raise_for_status()
            return JSONResponse(response.json())
    except Exception as exc:
        return JSONResponse(
            {"available": False, "reason": "Collector no disponible", "detail": type(exc).__name__},
            status_code=503,
        )

