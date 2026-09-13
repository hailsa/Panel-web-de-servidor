"""Static and slow-changing server details."""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Any

_hardware_cache: tuple[float, dict[str, Any]] = (0.0, {})
_disks_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])
_voltages_cache: tuple[float, list[dict[str, Any]]] = (0.0, [])
_services_cache: tuple[float, list[dict[str, str]]] = (0.0, [])


def _text(path: str) -> str | None:
    try:
        value = Path(path).read_text(encoding="utf-8", errors="replace").strip()
        return value or None
    except OSError:
        return None


def _run(command: list[str], timeout: float = 4.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def _mask_serial(serial: str | None) -> str:
    if not serial:
        return "No disponible"
    if len(serial) <= 4:
        return "•" * len(serial)
    return "•" * max(4, len(serial) - 4) + serial[-4:]


def collect_hardware(cache_seconds: int = 300) -> dict[str, Any]:
    global _hardware_cache
    now = time.monotonic()
    if now - _hardware_cache[0] < cache_seconds:
        return _hardware_cache[1]
    hardware = {
        "system_vendor": _text("/sys/class/dmi/id/sys_vendor") or "No disponible",
        "system_model": _text("/sys/class/dmi/id/product_name") or "No disponible",
        "board_vendor": _text("/sys/class/dmi/id/board_vendor") or "No disponible",
        "board_name": _text("/sys/class/dmi/id/board_name") or "No disponible",
        "board_version": _text("/sys/class/dmi/id/board_version") or "No disponible",
        "bios_vendor": _text("/sys/class/dmi/id/bios_vendor") or "No disponible",
        "bios_version": _text("/sys/class/dmi/id/bios_version") or "No disponible",
        "bios_date": _text("/sys/class/dmi/id/bios_date") or "No disponible",
    }
    _hardware_cache = (now, hardware)
    return hardware


def collect_physical_disks(cache_seconds: int = 30) -> list[dict[str, Any]]:
    global _disks_cache
    now = time.monotonic()
    if now - _disks_cache[0] < cache_seconds:
        return _disks_cache[1]
    ok, output = _run(
        ["lsblk", "-J", "-b", "-d", "-o", "NAME,PATH,MODEL,SERIAL,SIZE,TYPE,ROTA,TRAN,STATE"],
        timeout=4,
    )
    if not ok:
        return _disks_cache[1]
    try:
        devices = json.loads(output).get("blockdevices", [])
    except json.JSONDecodeError:
        return _disks_cache[1]
    rows: list[dict[str, Any]] = []
    for disk in devices:
        if disk.get("type") != "disk":
            continue
        rows.append(
            {
                "name": disk.get("name"),
                "path": disk.get("path"),
                "model": (disk.get("model") or "No disponible").strip(),
                "serial": _mask_serial(disk.get("serial")),
                "size": disk.get("size"),
                "rotational": bool(disk.get("rota")),
                "transport": disk.get("tran") or "No disponible",
                "state": disk.get("state") or "No disponible",
                "smart": {"available": False, "reason": "smartmontools no está instalado"},
            }
        )
    _disks_cache = (now, rows)
    return rows


def collect_voltages(cache_seconds: int = 10) -> list[dict[str, Any]]:
    global _voltages_cache
    now = time.monotonic()
    if now - _voltages_cache[0] < cache_seconds:
        return _voltages_cache[1]
    ok, output = _run(["sensors", "-j"], timeout=4)
    if not ok:
        return _voltages_cache[1]
    try:
        sensors = json.loads(output)
    except json.JSONDecodeError:
        return _voltages_cache[1]
    rows: list[dict[str, Any]] = []
    allowed = {"Vbat", "3VSB"}
    for source, adapter in sensors.items():
        if not isinstance(adapter, dict):
            continue
        for label, values in adapter.items():
            if label not in allowed or not isinstance(values, dict):
                continue
            value = next((number for key, number in values.items() if key.endswith("_input") and isinstance(number, (int, float))), None)
            if value is not None:
                rows.append({"source": source, "label": label, "volts": round(float(value), 3)})
    _voltages_cache = (now, rows)
    return rows


def collect_services(cache_seconds: int = 10) -> list[dict[str, str]]:
    global _services_cache
    now = time.monotonic()
    if now - _services_cache[0] < cache_seconds:
        return _services_cache[1]
    labels = {
        "apache2.service": "Apache",
        "docker.service": "Docker",
        "ssh.service": "SSH",
        "zerotier-one.service": "ZeroTier",
        "shc-collector.service": "SHC Collector",
    }
    rows: list[dict[str, str]] = []
    for unit, label in labels.items():
        ok, output = _run(["systemctl", "is-active", unit], timeout=2)
        rows.append({"name": label, "unit": unit, "state": output if output else ("active" if ok else "unknown")})
    _services_cache = (now, rows)
    return rows
