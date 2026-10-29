"""Bridge to the constrained host helper."""
import json
import subprocess
from fastapi import HTTPException


def vm_request(payload):
    try:
        result = subprocess.run(["sudo", "-n", "/usr/local/libexec/shc-vm-helper"],
                                input=json.dumps(payload), text=True, capture_output=True, timeout=110)
        data = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise HTTPException(503, "El gestor de máquinas virtuales no está disponible")
    if result.returncode or "error" in data:
        raise HTTPException(409, data.get("error", "Error al consultar libvirt"))
    if payload.get('action') not in {'list','detail','console','network-options','create-options','create-preview','browse-isos'}:
        from .collectors.virtual_machines import invalidate_virtual_machines
        invalidate_virtual_machines()
    return data
