"""Read-only host egress connection and Wi-Fi signal; no network probes."""
import json
from pathlib import Path
import subprocess


def wifi_signal(interface, content):
    for line in content.splitlines():
        name, separator, values = line.partition(':')
        if not separator or name.strip() != interface:
            continue
        fields = values.split()
        try:
            dbm = float(fields[2].rstrip('.'))
        except (IndexError, ValueError):
            return None
        if not -110 <= dbm <= -1:
            return None
        percent = round(max(0, min(100, 2 * (dbm + 100))))
        return {'signal_dbm': dbm, 'signal_percent': percent,
                'signal_bars': 3 if percent > 66 else 2 if percent > 33 else 1,
                'signal_estimated': True}
    return None


def _read(path):
    try:
        return Path(path).read_text(encoding='utf-8')
    except OSError:
        return ''


def collect_connection():
    """Ask the routing table which interface handles ordinary outbound IPv4."""
    result = {'type': 'unknown', 'interface': None, 'signal_bars': None,
              'signal_percent': None, 'signal_dbm': None}
    try:
        route = subprocess.run(['ip', '-j', 'route', 'get', '1.1.1.1'],
                               capture_output=True, text=True, timeout=1.5)
        rows = json.loads(route.stdout) if route.returncode == 0 else []
        if not rows:
            route = subprocess.run(['ip', '-j', '-6', 'route', 'show', 'default'],
                                   capture_output=True, text=True, timeout=1.5)
            rows = sorted(json.loads(route.stdout), key=lambda row: row.get('metric', 0)) if route.returncode == 0 else []
        if not rows:
            return {**result, 'type': 'disconnected'}
        interface = rows[0].get('dev', '')
        if not interface or '/' in interface or interface in {'.', '..'}:
            return result
        result['interface'] = interface
        device = Path('/sys/class/net') / interface
        if (device / 'wireless').is_dir() or (device / 'phy80211').exists():
            result['type'] = 'wifi'
            result.update(wifi_signal(interface, _read('/proc/net/wireless')) or {})
        elif (device / 'device').exists() and _read(device / 'type').strip() == '1':
            result['type'] = 'ethernet'
        else:
            result['type'] = 'other'
    except (OSError, ValueError, TypeError, AttributeError, KeyError, subprocess.TimeoutExpired):
        pass
    return result
