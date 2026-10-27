"""Listening sockets with process names and Docker publishing information."""
import json
import re
import socket
import subprocess
import threading
import time

_cache = (0.0, [])
_lock = threading.Lock()


def run(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=4)
        return result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def service_name(port, protocol, processes, containers):
    names = set(processes)
    if 'zerotier-one' in names:
        return 'ZeroTier', 'process'
    if 'containerd' in names:
        return 'containerd', 'process'
    if names.intersection({'sshd', 'sshd-session'}):
        return 'SSH', 'process'
    if 'apache2' in names or 'httpd' in names:
        return {80: 'HTTP · Apache', 443: 'HTTPS · Apache'}.get(port, 'Apache'), 'process'
    if any(name.startswith('qemu') for name in names) and 5900 <= port <= 5999:
        return 'VNC · KVM', 'process'
    if any(name.startswith('cockpit') for name in names):
        return 'Cockpit', 'process'
    if 'dnsmasq' in names:
        return {53: 'DNS · dnsmasq', 67: 'DHCP · dnsmasq'}.get(port, 'dnsmasq'), 'process'
    if (port, protocol) in containers:
        name = containers[(port, protocol)]
        return ('SHC Monitor' if name == 'shc-monitor' else name) + ' · Docker', 'container'
    if processes:
        return ', '.join(processes), 'process'
    try:
        return socket.getservbyport(port, protocol), 'port'
    except OSError:
        return 'No identificado', 'unknown'


def collect_ports(cache_seconds=15):
    global _cache
    with _lock:
        now = time.monotonic()
        if now - _cache[0] < cache_seconds:
            return _cache[1]
        output = run(['sudo', '-n', '/usr/bin/ss', '-H', '-lntup'])
        if output is None:
            output = run(['ss', '-H', '-lntup']) or ''
        containers = {}
        for line in (run(['docker', 'ps', '--format', '{{json .}}']) or '').splitlines():
            try:
                item = json.loads(line)
            except ValueError:
                continue
            for port, protocol in re.findall(r':(\d+)->\d+/(tcp|udp)', item.get('Ports', '')):
                containers[(int(port), protocol)] = item.get('Names', 'Docker')
        rows = {}
        for line in output.splitlines():
            parts = line.split()
            if len(parts) < 6:
                continue
            protocol, address = parts[0], parts[4]
            port = address.rsplit(':', 1)[-1]
            if not port.isdigit() or protocol not in {'tcp', 'udp'}:
                continue
            processes = list(dict.fromkeys(re.findall(r'\("([^"\n]+)",pid=', line)))
            service, source = service_name(int(port), protocol, processes, containers)
            rows[(protocol,address)] = {'protocol':protocol, 'address':address, 'port':int(port),
                                        'process': ', '.join(processes), 'service':service, 'service_source':source}
        result = sorted(rows.values(), key=lambda item:(item['port'], item['protocol'], item['address']))
        _cache = (now,result)
        return result
