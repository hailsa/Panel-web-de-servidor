"""Low-cost, read-only snapshot of the Debian host."""

from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

_sample_lock = threading.Lock()
_last_network_sample: tuple[float, int, int] | None = None


def _run(command: list[str], timeout: float = 3.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"},
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def _os_release() -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip('"')
    except OSError:
        pass
    return values


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "No disponible"


def _addresses() -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for interface, addresses in psutil.net_if_addrs().items():
        for address in addresses:
            if address.family == socket.AF_INET:
                result.append({"interface": interface, "address": address.address, "netmask": address.netmask or ""})
    return result


def _filesystems() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    ignored = {"tmpfs", "devtmpfs", "overlay", "squashfs", "nsfs"}
    for partition in psutil.disk_partitions(all=False):
        if partition.fstype in ignored or not partition.device.startswith("/dev/"):
            continue
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except (OSError, PermissionError):
            continue
        rows.append(
            {
                "device": partition.device,
                "mountpoint": partition.mountpoint,
                "fstype": partition.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
            }
        )
    return rows


def _temperatures() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        groups = psutil.sensors_temperatures(fahrenheit=False)
    except (AttributeError, OSError):
        return rows
    for source, entries in groups.items():
        for entry in entries:
            value = float(entry.current)
            if value <= -50 or value >= 150:
                continue
            rows.append(
                {
                    "source": source,
                    "label": entry.label or source,
                    "current_c": round(value, 1),
                    "high_c": entry.high,
                    "critical_c": entry.critical,
                }
            )
    return rows


def _fans() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        groups = psutil.sensors_fans()
    except (AttributeError, OSError):
        return rows
    for source, entries in groups.items():
        for entry in entries:
            if entry.current > 0:
                rows.append({"source": source, "label": entry.label or source, "rpm": entry.current})
    return rows


def _docker() -> dict[str, Any]:
    ok, output = _run(["docker", "ps", "-a", "--format", "{{json .}}"], timeout=5)
    if not ok:
        return {"available": False, "reason": output, "containers": []}
    containers: list[dict[str, Any]] = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        containers.append(
            {
                "name": item.get("Names", ""),
                "image": item.get("Image", ""),
                "state": item.get("State", "unknown"),
                "status": item.get("Status", ""),
            }
        )
    return {"available": True, "containers": containers}


def _network_rates(net: Any) -> tuple[float, float]:
    global _last_network_sample
    now = time.monotonic()
    with _sample_lock:
        previous = _last_network_sample
        _last_network_sample = (now, net.bytes_sent, net.bytes_recv)
    if previous is None:
        return 0.0, 0.0
    elapsed = max(0.001, now - previous[0])
    sent = max(0, net.bytes_sent - previous[1]) / elapsed
    received = max(0, net.bytes_recv - previous[2]) / elapsed
    return round(sent, 1), round(received, 1)


def _internet_available() -> bool:
    """Check outbound connectivity without depending on DNS."""
    try:
        with socket.create_connection(("1.1.1.1", 53), timeout=1.2):
            return True
    except OSError:
        return False


def _top_processes(limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with _sample_lock:
        for process in psutil.process_iter(["pid", "name", "memory_percent"]):
            try:
                rows.append(
                    {
                        "pid": process.pid,
                        "name": process.info.get("name") or "desconocido",
                        "cpu_percent": round(process.cpu_percent(interval=None), 1),
                        "memory_percent": round(float(process.info.get("memory_percent") or 0), 1),
                    }
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
    rows.sort(key=lambda item: (item["cpu_percent"], item["memory_percent"]), reverse=True)
    return rows[:limit]


def _ports() -> list[dict[str, Any]]:
    ok, output = _run(["ss", "-H", "-lntup"], timeout=3)
    if not ok:
        return []
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local = parts[4]
        port = local.rsplit(":", 1)[-1]
        if not port.isdigit():
            continue
        rows.append({"protocol": parts[0], "address": local, "port": int(port), "process": " ".join(parts[6:])})
    unique = {(row["protocol"], row["address"], row["port"]): row for row in rows}
    return sorted(unique.values(), key=lambda item: (item["port"], item["protocol"]))


def _raid() -> dict[str, Any]:
    path = Path("/proc/mdstat")
    if not path.exists():
        return {"available": False, "configured": False, "reason": "No se detectó Linux MD RAID"}
    content = path.read_text(encoding="utf-8", errors="replace")
    configured = any(line.startswith("md") for line in content.splitlines())
    return {"available": True, "configured": configured, "raw": content if configured else ""}


def collect_snapshot() -> dict[str, Any]:
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    uptime = max(0, int(time.time() - psutil.boot_time()))
    frequencies = psutil.cpu_freq()
    net = psutil.net_io_counters()
    bytes_sent_per_second, bytes_received_per_second = _network_rates(net)
    temperatures = _temperatures()
    cpu_package = next(
        (item for item in temperatures if item["source"] == "coretemp" and "Package" in item["label"]),
        temperatures[0] if temperatures else None,
    )
    os_release = _os_release()
    return {
        "available": True,
        "collected_at": datetime.now(UTC).isoformat(),
        "system": {
            "hostname": platform.node(),
            "os": os_release.get("PRETTY_NAME", platform.platform()),
            "kernel": platform.release(),
            "architecture": platform.machine(),
            "cpu_model": _cpu_model(),
            "cpu_count": psutil.cpu_count(logical=True),
            "uptime_seconds": uptime,
        },
        "cpu": {
            "percent": psutil.cpu_percent(interval=0.15),
            "frequency_mhz": round(frequencies.current, 0) if frequencies else None,
            "load_average": list(os.getloadavg()),
            "temperature_c": cpu_package["current_c"] if cpu_package else None,
        },
        "memory": {
            "total": memory.total,
            "used": memory.used,
            "available": memory.available,
            "percent": memory.percent,
            "swap_total": swap.total,
            "swap_used": swap.used,
        },
        "network": {
            "addresses": _addresses(),
            "bytes_sent": net.bytes_sent,
            "bytes_received": net.bytes_recv,
            "errors_in": net.errin,
            "errors_out": net.errout,
            "bytes_sent_per_second": bytes_sent_per_second,
            "bytes_received_per_second": bytes_received_per_second,
            "internet_available": _internet_available(),
        },
        "processes": _top_processes(),
        "filesystems": _filesystems(),
        "temperatures": temperatures,
        "fans": _fans(),
        "docker": _docker(),
        "ports": _ports(),
        "raid": _raid(),
        "virtual_machines": {"available": False, "reason": "No se detectó libvirt", "machines": []},
        "smart": {"available": False, "reason": "smartmontools no está instalado"},
    }
