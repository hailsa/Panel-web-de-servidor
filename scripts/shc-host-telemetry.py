#!/usr/bin/python3
"""Fixed read-only queries. Never return disk serials or firmware identifiers."""
import json
from pathlib import Path
import subprocess
import sys


def command(*args):
    return subprocess.run(args, capture_output=True, text=True, timeout=4, check=False).stdout


def smart():
    rows = {}
    for device in sorted(Path('/sys/block').iterdir()):
        if not (device / 'device').exists() and not device.name.startswith('nvme'):
            continue
        try:
            data = json.loads(command('/usr/sbin/smartctl', '-AjH', '/dev/' + device.name))
        except (ValueError, OSError, subprocess.TimeoutExpired):
            continue
        nvme = data.get('nvme_smart_health_information_log', {})
        ata = {attr['id']: attr for attr in data.get('ata_smart_attributes', {}).get('table', [])}
        counters = {'Sectores reasignados': ata.get(5, {}).get('raw', {}).get('value'),
                    'Sectores pendientes': ata.get(197, {}).get('raw', {}).get('value'),
                    'Sectores incorregibles': ata.get(198, {}).get('raw', {}).get('value'),
                    'Errores de medio NVMe': nvme.get('media_errors'),
                    'Alerta crítica NVMe': nvme.get('critical_warning')}
        failed = [attr['name'] for attr in ata.values() if attr.get('when_failed') not in {None, '', '-'}]
        hours = data.get('power_on_time', {}).get('hours', nvme.get('power_on_hours'))
        cycles = data.get('power_cycle_count', nvme.get('power_cycles', ata.get(12, {}).get('raw', {}).get('value')))
        health = data.get('smart_status', {}).get('passed')
        rows[device.name] = {
            'available': health is not None or hours is not None or bool(ata or nvme),
            'passed': health, 'hours': hours, 'cycles': cycles,
            'temperature': data.get('temperature', {}).get('current', nvme.get('temperature')),
            'wear_percent': nvme.get('percentage_used'),
            'warnings': [f'{label}: {value}' for label, value in counters.items() if value] + failed,
            'reason': 'El disco no devolvió datos SMART',
        }
    return rows


def hardware():
    output = command('/usr/sbin/dmidecode', '-t', '17')
    allowed = {'Size', 'Locator', 'Type', 'Speed', 'Configured Memory Speed', 'Manufacturer', 'Part Number', 'Rank'}
    return [{k.strip(): v.strip() for line in block.splitlines() if ':' in line
             for k, v in [line.split(':', 1)] if k.strip() in allowed}
            for block in output.split('Memory Device\n')[1:]]


def energy():
    rows = {}
    for path in Path('/sys/class/powercap').glob('intel-rapl:[0-9]*'):
        if path.name.count(':') != 1:
            continue
        try:
            rows[(path / 'name').read_text().strip()] = [int((path / name).read_text())
                for name in ('energy_uj', 'max_energy_range_uj')]
        except (OSError, ValueError):
            continue
    return rows


if __name__ == '__main__':
    actions = {'smart': smart, 'hardware': hardware, 'energy': energy}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        sys.exit(2)
    try:
        print(json.dumps(actions[sys.argv[1]]()))
    except (OSError, subprocess.TimeoutExpired):
        sys.exit(1)
