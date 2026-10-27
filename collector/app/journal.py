"""Read-only system journal bridge with bounded concurrency."""
import json
import subprocess
import threading
import time
from fastapi import HTTPException

_gate=threading.BoundedSemaphore(2)
_metadata=(0.0,None)


def journal_request(payload):
    global _metadata
    if payload.get('action')=='metadata' and _metadata[1] is not None and time.monotonic()-_metadata[0]<60:
        return _metadata[1]
    if not _gate.acquire(blocking=False):raise HTTPException(429,'Hay consultas en curso; intentá nuevamente en unos segundos')
    try:
        result=subprocess.run(['sudo','-n','/usr/local/libexec/shc-journal-helper'],
                              input=json.dumps(payload),text=True,capture_output=True,timeout=40)
        try:data=json.loads(result.stdout)
        except ValueError:raise HTTPException(503,'El visor no tiene acceso al journal completo')
        if result.returncode or 'error' in data:raise HTTPException(400,data.get('error','Consulta rechazada'))
        if payload.get('action')=='metadata':_metadata=(time.monotonic(),data)
        return data
    except (OSError,subprocess.TimeoutExpired):
        raise HTTPException(503,'La consulta tardó demasiado; reducí el período o elegí un servicio')
    finally:_gate.release()
