"""Correlate active logind sessions with completed login records."""
import ipaddress
import os
import re
import subprocess


def run(*args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=2, check=False,
                              env={**os.environ, 'LC_ALL': 'C'}).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ''


def source(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return 'Local o sin dirección IP', None
    if ip in ipaddress.ip_network('10.0.0.0/8'):
        return 'Red privada / VPN', None
    return ('IP pública', str(ip)) if ip.is_global else ('Red local o privada', None)


def active_sessions():
    previous = {}
    for line in run('last', '-n', '200', '-w', '-i', '-F').splitlines():
        match = re.match(r'^(\S+)\s+(pts/\d+|tty\d+)\s+(\S+)\s+(.+?)\s+-\s+\w{3} ', line)
        if match:
            username, tty, address, timestamp = match.groups()
            previous.setdefault(username, {'address': address, 'timestamp': timestamp, 'tty': tty})
    sessions = []
    for line in run('loginctl', 'list-sessions', '--no-legend').splitlines()[:40]:
        identifier = line.split()[0]
        props = dict(line.split('=', 1) for line in run('loginctl', 'show-session', identifier, '-p', 'Name',
                     '-p', 'Remote', '-p', 'RemoteHost', '-p', 'Service', '-p', 'Class', '-p', 'TTY',
                     '-p', 'Timestamp', '-p', 'State').splitlines() if '=' in line)
        if props.get('Class') not in {'user', 'user-light', 'user-early'}:
            continue
        address = props.get('RemoteHost', '')
        location, public_ip = source(address)
        sessions.append({'user': props.get('Name'), 'service': props.get('Service'),
                         'ssh': props.get('Service', '').startswith('ssh'), 'address': address,
                         'network': location, 'public_ip': public_ip, 'device': props.get('TTY'),
                         'timestamp': props.get('Timestamp'), 'state': props.get('State'),
                         'previous': previous.get(props.get('Name'))})
    return sessions
