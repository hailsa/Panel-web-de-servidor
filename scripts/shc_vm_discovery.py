"""Passive IP hints for guests without an agent, including macvtap/static IPs.

Only Ethernet/ARP/IP headers are inspected. No payload or packet capture is saved.
"""
import ipaddress
import json
import os
from pathlib import Path
import select
import socket
import tempfile
import time

RETENTION = 3600
CACHE_DIR = Path('/run/shc-vm-network')


def packet_address(frame, allowed_macs):
    if len(frame) < 14:
        return None
    mac = ':'.join(f'{byte:02x}' for byte in frame[6:12])
    if mac not in allowed_macs:
        return None
    kind, offset = int.from_bytes(frame[12:14], 'big'), 14
    for _ in range(2):
        if kind not in (0x8100, 0x88a8):
            break
        if len(frame) < offset + 4:
            return None
        kind, offset = int.from_bytes(frame[offset + 2:offset + 4], 'big'), offset + 4
    if kind == 0x0806 and len(frame) >= offset + 28:
        arp = frame[offset:offset + 28]
        if arp[:6] != b'\x00\x01\x08\x00\x06\x04' or arp[6:8] not in (b'\x00\x01', b'\x00\x02') or arp[8:14] != frame[6:12]:
            return None
        packed = arp[14:18]
    elif kind == 0x0800 and len(frame) >= offset + 20 and frame[offset] >> 4 == 4:
        if frame[offset] & 15 < 5:
            return None
        packed = frame[offset + 12:offset + 16]
    elif kind == 0x86dd and len(frame) >= offset + 40 and frame[offset] >> 4 == 6:
        packed = frame[offset + 8:offset + 24]
    else:
        return None
    address = ipaddress.ip_address(packed)
    if address.is_loopback or address.is_unspecified or address.is_multicast or str(address) == '255.255.255.255':
        return None
    return {'mac': mac, 'address': f'{address}/{address.max_prefixlen}', 'family': address.version,
            'link_local': address.is_link_local, 'source': 'traffic', 'prefix_known': False}


def sample_headers(targets, duration=0.8):
    sockets, result = {}, []
    try:
        for device, macs in list(targets.items())[:8]:
            stream = None
            try:
                stream = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
                stream.bind((device, 0))
                stream.setblocking(False)
                sockets[stream] = macs
            except OSError:
                if stream is not None:
                    stream.close()
        deadline, frames = time.monotonic() + duration, 0
        while sockets and time.monotonic() < deadline and frames < 4096:
            ready, _, _ = select.select(list(sockets), [], [], max(0, deadline - time.monotonic()))
            for stream in ready:
                try:
                    # 64 bytes suffice even for double-tagged IPv6 headers.
                    frame = stream.recv(64)
                except OSError:
                    continue
                frames += 1
                item = packet_address(frame, sockets[stream])
                if item:
                    item['observed_at'] = int(time.time())
                    result.append(item)
    finally:
        for stream in sockets:
            stream.close()
    return result


def discover_addresses(root, domain, known, cache_dir=CACHE_DIR):
    targets, identity = {}, []
    for node in root.findall('devices/interface'):
        mac, source, target = node.find('mac'), node.find('source'), node.find('target')
        if mac is None or source is None:
            continue
        address = mac.get('address', '').lower()
        kind = node.get('type')
        device = (source.get('dev') if kind == 'direct' else source.get('bridge') if kind == 'bridge'
                  else target.get('dev') if target is not None and kind == 'network' else None)
        identity.append([address, kind, sorted(source.attrib.items())])
        if device and node.find("link[@state='down']") is None:
            targets.setdefault(device, set()).add(address)
    fingerprint = json.dumps([root.get('id'), identity], sort_keys=True)
    now, cache = time.time(), {}
    path = cache_dir / f'{domain}.json'
    try:
        if path.stat().st_size <= 65536:
            cache = json.loads(path.read_text())
        if not isinstance(cache, dict) or cache.get('identity') != fingerprint:
            cache = {}
    except (OSError, ValueError):
        pass
    allowed = set().union(*targets.values()) if targets else set()
    retained = []
    entries = cache.get('addresses', [])
    for item in entries if isinstance(entries, list) else []:
        try:
            if item['mac'] in allowed and 0 <= now - item['observed_at'] < RETENTION:
                ipaddress.ip_interface(item['address'])
                retained.append(item)
        except (KeyError, TypeError, ValueError):
            continue
    authoritative = {item['mac'] for item in known if item['source'] in {'agent', 'lease'}}
    targets = {device: macs - authoritative for device, macs in targets.items() if macs - authoritative}
    observations = []
    sampled_at = cache.get('sampled_at', 0)
    if not isinstance(sampled_at, (int, float)):
        sampled_at = 0
    if targets and (not retained or now - sampled_at >= 10):
        observations = sample_headers(targets)
        cache['sampled_at'] = now
    unique = {(item['mac'], item['address']): item for item in retained + observations}
    result = sorted(unique.values(), key=lambda item: item['observed_at'], reverse=True)[:32]
    try:
        cache_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', dir=cache_dir, delete=False) as file:
            temporary = file.name
            json.dump({'identity': fingerprint, 'sampled_at': cache.get('sampled_at', 0), 'addresses': result}, file)
        os.replace(temporary, path)
    except OSError:
        if 'temporary' in locals():
            Path(temporary).unlink(missing_ok=True)
    return result
