#!/usr/bin/python3
"""Constrained JSON boundary; workers are launched by systemd, never by sudo arguments."""
import json
import os
import sys
from shc_updates import handle, run_worker, queue_job

if __name__ == '__main__':
    try:
        os.umask(0o077)
        if os.geteuid() != 0:
            raise ValueError('Se requiere el helper autorizado del servidor.')
        if len(sys.argv) == 3 and sys.argv[1] == '--worker':
            run_worker(sys.argv[2])
        elif sys.argv[1:] == ['--scheduled']:
            queue_job('refresh')
        elif len(sys.argv) == 1:
            raw = sys.stdin.read(16385)
            if len(raw) > 16384:
                raise ValueError('Solicitud demasiado grande.')
            request = json.loads(raw)
            if not isinstance(request, dict):
                raise ValueError('Solicitud inválida.')
            print(json.dumps(handle(request), ensure_ascii=False))
        else:
            raise ValueError('Argumentos no permitidos.')
    except Exception as error:
        print(json.dumps({'error': str(error)[:1800]}, ensure_ascii=False))
        sys.exit(1)
