"""Local accounts and revocable browser sessions."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path

import bcrypt

DB_PATH = Path(os.getenv("SHC_AUTH_DB", "/var/lib/shc-monitor/auth/auth.sqlite3"))
SESSION_SECONDS = 12 * 60 * 60


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1)")
        db.execute("CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, expires_at INTEGER NOT NULL)")
        db.execute("CREATE INDEX IF NOT EXISTS sessions_expires ON sessions(expires_at)")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    if encoded.startswith("$2"):
        return bcrypt.checkpw(password.encode(), encoded.encode())
    try:
        algorithm, salt, expected = encoded.split("$", 2)
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def set_user(username: str, password: str) -> None:
    if not username or len(password) < 4:
        raise ValueError("Usuario o contraseña inválidos")
    init_db()
    with connect() as db:
        db.execute("INSERT INTO users(username,password_hash) VALUES(?,?) ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash, enabled=1", (username, hash_password(password)))


def import_htpasswd(username: str, encoded: str) -> None:
    init_db()
    with connect() as db:
        db.execute("INSERT OR IGNORE INTO users(username,password_hash) VALUES(?,?)", (username, encoded))


def authenticate(username: str, password: str) -> str | None:
    with connect() as db:
        row = db.execute("SELECT password_hash, enabled FROM users WHERE username=?", (username,)).fetchone()
    if not row or not row["enabled"] or not verify_password(password, row["password_hash"]):
        return None
    token = secrets.token_urlsafe(32)
    with connect() as db:
        db.execute("INSERT INTO sessions(token_hash,username,expires_at) VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), username, int(time.time()) + SESSION_SECONDS))
    return token


def session_user(token: str | None) -> str | None:
    if not token:
        return None
    with connect() as db:
        row = db.execute("SELECT username FROM sessions WHERE token_hash=? AND expires_at>?", (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
    return row["username"] if row else None


def revoke(token: str | None) -> None:
    if token:
        with connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
