"""Read-only inventory of local users and their roles."""

from __future__ import annotations

import grp
import pwd
import subprocess
import time
from typing import Any

import psutil

_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])


def _last_access() -> dict[str, str]:
    try:
        result = subprocess.run(
            ["last", "-n", "250", "-w", "-F"],
            check=False,
            capture_output=True,
            text=True,
            timeout=4,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    access: dict[str, str] = {}
    for line in result.stdout.splitlines():
        fields = line.split()
        if not fields or fields[0] in {"reboot", "shutdown", "wtmp"}:
            continue
        username = fields[0]
        if username not in access:
            access[username] = " ".join(fields[3:8]) if len(fields) >= 8 else "Registrado"
    return access


def _groups_by_user() -> dict[str, set[str]]:
    memberships: dict[str, set[str]] = {}
    for group in grp.getgrall():
        for username in group.gr_mem:
            memberships.setdefault(username, set()).add(group.gr_name)
    return memberships


def _role(uid: int, groups: set[str], interactive: bool) -> str:
    if uid == 0:
        return "Administrador"
    if groups.intersection({"sudo", "wheel"}):
        return "Administrador / privilegiado"
    if uid >= 1000 and interactive:
        return "Usuario"
    return "Sistema"


def collect_users(cache_seconds: int = 30) -> list[dict[str, Any]]:
    global _cache
    now = time.monotonic()
    if now - _cache[0] < cache_seconds:
        return _cache[1]

    memberships = _groups_by_user()
    last_access = _last_access()
    online = {item.name for item in psutil.users()}
    rows: list[dict[str, Any]] = []

    for account in pwd.getpwall():
        try:
            primary_group = grp.getgrgid(account.pw_gid).gr_name
        except KeyError:
            primary_group = str(account.pw_gid)
        groups = memberships.get(account.pw_name, set()).copy()
        groups.add(primary_group)
        interactive = not account.pw_shell.endswith(("/nologin", "/false"))
        if account.pw_name in online:
            state = "En línea"
        elif not interactive:
            state = "Sin login"
        else:
            state = "Activo"
        rows.append(
            {
                "username": account.pw_name,
                "uid": account.pw_uid,
                "primary_group": primary_group,
                "groups": sorted(groups),
                "role": _role(account.pw_uid, groups, interactive),
                "shell": account.pw_shell,
                "home": account.pw_dir,
                "last_access": last_access.get(account.pw_name, "No registrado"),
                "state": state,
            }
        )

    rows.sort(key=lambda item: (item["role"] == "Sistema", item["uid"], item["username"]))
    _cache = (now, rows)
    return rows
