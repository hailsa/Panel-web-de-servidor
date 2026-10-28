#!/usr/bin/python3
"""One-shot media linking; receives only a UUID of a root-owned request."""
import json
import os
from pathlib import Path
import sys
import uuid
from shc_vm_create import link_media

identity=str(uuid.UUID(sys.argv[1]))
job=Path('/run/shc-vm-creator/iso-jobs')/(identity+'.json')
descriptor=os.open(job,os.O_RDONLY|os.O_NOFOLLOW)
try:
    info=os.fstat(descriptor)
    if info.st_uid!=0 or info.st_mode&0o022:raise ValueError('Solicitud de medios inválida')
    with os.fdopen(descriptor) as handle:request=json.load(handle)
    try:request['result']={'path':link_media(request['source'])}
    except Exception as exc:request['result']={'error':str(exc)[:400]}
    job.write_text(json.dumps(request));job.chmod(0o600)
except Exception:
    raise
