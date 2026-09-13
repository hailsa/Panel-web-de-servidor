"""Authentication shared by all protected collector routes."""

from __future__ import annotations

import hmac
import os
from functools import lru_cache
from pathlib import Path

from fastapi import Header, HTTPException, status


@lru_cache(maxsize=1)
def collector_token() -> str:
    path = Path(os.getenv("SHC_COLLECTOR_TOKEN_FILE", "/etc/shc-monitor/collector-token"))
    token = path.read_text(encoding="utf-8").strip()
    if len(token) < 32:
        raise RuntimeError("Collector token is missing or too short")
    return token


def require_token(authorization: str | None = Header(default=None)) -> None:
    expected = f"Bearer {collector_token()}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

