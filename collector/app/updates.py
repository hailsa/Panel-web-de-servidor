"""Authenticated bridge to the constrained APT helper."""
import json
import subprocess
from fastapi import HTTPException


def updates_request(payload):
    try:
        result = subprocess.run(['sudo', '-n', '/usr/local/libexec/shc-updates-helper'],
                                input=json.dumps(payload), text=True, capture_output=True, timeout=110)
        data = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise HTTPException(503, 'No se pudo consultar el gestor de actualizaciones.')
    if result.returncode or 'error' in data:
        raise HTTPException(409, data.get('error', 'No se pudo completar la operación de APT.'))
    return data
