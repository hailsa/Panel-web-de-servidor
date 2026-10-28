"""Read-only libvirt inventory, cached to keep dashboard polling inexpensive."""

import os
import subprocess
import threading
import time

_lock = threading.Lock()
_cache = (0.0, None)


def _virsh(*arguments):
    result = subprocess.run(
        ["virsh", "--readonly", "--connect", "qemu:///system", *arguments],
        capture_output=True, text=True, timeout=4,
        env={**os.environ, "LC_ALL": "C", "LANG": "C"},
    )
    if result.returncode:
        raise RuntimeError("libvirt query failed")
    return result.stdout.strip()


def invalidate_virtual_machines():
    global _cache
    with _lock:_cache=(0.0,None)


def collect_virtual_machines(cache_seconds=5):
    global _cache
    with _lock:
        now = time.monotonic()
        if _cache[1] is not None and now - _cache[0] < cache_seconds:
            return _cache[1]
        try:
            names = _virsh("list", "--all", "--name").splitlines()
            machines = []
            for name in names:
                if not name.strip():
                    continue
                state = _virsh("domstate", "--domain", name).strip()
                machines.append({"name": name, "state": state})
            data = {"available": True, "provider": "KVM / libvirt", "machines": machines}
        except (OSError, subprocess.TimeoutExpired, RuntimeError):
            data = {"available": False, "reason": "No se pudo consultar KVM / libvirt en modo de sólo lectura", "machines": []}
        _cache = (now, data)
        return data
