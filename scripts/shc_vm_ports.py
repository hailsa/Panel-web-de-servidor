"""Read the guest's own socket table through QEMU Guest Agent."""
import base64
import json
import subprocess
import time

LINUX_COMMAND = ['/usr/bin/ss', '-H', '-lntu']
WINDOWS_COMMAND = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
    "$ErrorActionPreference='Stop'; @((Get-NetTCPConnection -State Listen | ForEach-Object { @{protocol='tcp';address=$_.LocalAddress;port=$_.LocalPort} }); (Get-NetUDPEndpoint | ForEach-Object { @{protocol='udp';address=$_.LocalAddress;port=$_.LocalPort} })) | ConvertTo-Json -Compress"]


def ports(virsh, domain):
    def agent(execute, arguments=None):
        payload = {'execute': execute}
        if arguments is not None:
            payload['arguments'] = arguments
        return json.loads(virsh('qemu-agent-command', '--domain', domain, '--timeout', '1',
                                json.dumps(payload), timeout=2))['return']

    try:
        os_info = agent('guest-get-osinfo')
        windows = os_info.get('id') == 'mswindows'
        command = WINDOWS_COMMAND if windows else LINUX_COMMAND
        job = agent('guest-exec', {'path': command[0], 'arg': command[1:], 'capture-output': True})
        until = time.monotonic() + 8
        while time.monotonic() < until:
            status = agent('guest-exec-status', {'pid': job['pid']})
            if not status.get('exited'):
                time.sleep(0.25)
                continue
            if status.get('exitcode') != 0 or status.get('out-truncated'):
                break
            output = base64.b64decode(status.get('out-data', '')).decode('utf-8-sig')
            if windows:
                rows = json.loads(output) if output.strip() else []
                rows = rows if isinstance(rows, list) else [rows]
            else:
                rows = []
                for line in output.splitlines():
                    fields = line.split()
                    if len(fields) >= 5:
                        address, _, port = fields[4].rpartition(':')
                        if port.isdigit():
                            rows.append({'protocol': fields[0], 'address': address, 'port': int(port)})
            return {'available': True, 'ports': rows[:2000], 'truncated': len(rows) > 2000}
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired):
        pass
    return {'available': False, 'reason': 'Se requiere QEMU Guest Agent activo con guest-exec y la herramienta de sockets del invitado.'}
