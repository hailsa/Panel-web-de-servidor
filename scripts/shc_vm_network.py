"""Validated NIC configuration; never changes the host's network configuration."""
import copy
import ipaddress
from pathlib import Path
import re
import secrets
import xml.etree.ElementTree as ET

MODELS = ('e1000e', 'virtio', 'e1000', 'rtl8139')
MAC = re.compile(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}')


def parse_addresses(text, source):
    addresses = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 4 or parts[2] not in {'ipv4', 'ipv6'} or not MAC.fullmatch(parts[1].lower()):
            continue
        try:
            address = ipaddress.ip_interface(parts[3])
        except ValueError:
            continue
        if address.ip.is_loopback or address.ip.is_unspecified or address.ip.is_multicast:
            continue
        addresses.append({'mac': parts[1].lower(), 'address': str(address), 'source': source,
                          'family': address.version, 'link_local': address.ip.is_link_local})
    return addresses


def network_options(virsh, sys_class=Path('/sys/class/net')):
    networks, bridges, physical = [], [], []
    managed_bridges = set()
    for net_id in virsh('net-list', '--all', '--uuid').splitlines():
        root = ET.fromstring(virsh('net-dumpxml', net_id))
        name = root.findtext('name', '')
        bridge, forward = root.find('bridge'), root.find('forward')
        if bridge is not None:
            managed_bridges.add(bridge.get('name'))
        info = virsh('net-info', net_id)
        active = any(line.split(':', 1)[0].strip() == 'Active' and line.split(':', 1)[1].strip() == 'yes'
                     for line in info.splitlines() if ':' in line)
        networks.append({'name': name, 'mode': forward.get('mode') if forward is not None else 'isolated',
                         'active': active})
    for path in sorted(sys_class.iterdir()):
        name = path.name
        if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,15}', name):
            continue
        up = (path / 'operstate').read_text().strip() == 'up'
        item = {'name': name, 'up': up, 'mtu': int((path / 'mtu').read_text().strip())}
        if (path / 'bridge').is_dir() and name not in managed_bridges and name != 'docker0' and not name.startswith('br-'):
            item['members'] = [member.name for member in (path / 'brif').iterdir()]
            item['lan'] = any((sys_class / member / 'device').exists() for member in item['members'])
            bridges.append(item)
        elif (path / 'device').exists() and not (path / 'wireless').exists() and not (path / 'master').exists():
            physical.append(item)
    return {'networks': networks, 'bridges': bridges, 'physical': physical, 'models': list(MODELS)}


def interface_details(node, addresses):
    def attribute(tag, key, default=''):
        child = node.find(tag)
        return child.get(key, default) if child is not None else default
    mac = attribute('mac', 'address')
    source = node.find('source')
    found, seen = [], set()
    for item in addresses:
        address_key = str(ipaddress.ip_interface(item['address']).ip)
        if item['mac'] == mac.lower() and address_key not in seen:
            found.append(item)
            seen.add(address_key)
    return {'type': node.get('type'), 'mac': mac, 'model': attribute('model', 'type'),
            'source': dict(source.attrib) if source is not None else {}, 'addresses': found,
            'link_state': attribute('link', 'state', 'up'), 'mtu': attribute('mtu', 'size'),
            'queues': attribute('driver', 'queues'), 'target': attribute('target', 'dev'),
            'editable': node.get('type') in {'network', 'bridge', 'direct'}}


def number(value, label, low, high):
    if value in ('', None):
        return None
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,7}', str(value)) or not low <= int(value) <= high:
        raise ValueError(f'{label}: valor fuera del rango {low}–{high}.')
    return int(value)


def configure_interface(root, payload, options):
    """Change a copy of the inactive XML, preserving unrelated devices and policies."""
    root = copy.deepcopy(root)
    devices = root.find('devices')
    adding = payload['action'] == 'network-add'
    if adding:
        node = ET.Element('interface')
        devices.append(node)
    else:
        selector = str(payload.get('interface_mac', '')).lower()
        matches = [item for item in devices.findall('interface')
                   if item.find('mac') is not None and item.find('mac').get('address', '').lower() == selector]
        if len(matches) != 1:
            raise ValueError('La interfaz cambió o ya no existe. Actualizá la vista.')
        node = matches[0]
        if node.get('type') not in {'network', 'bridge', 'direct'}:
            raise ValueError('Este tipo de interfaz debe configurarse desde el hipervisor.')
    kind, source = payload.get('network_type'), payload.get('source')
    if kind not in {'network', 'bridge', 'direct'}:
        raise ValueError('Tipo de conexión no permitido.')
    collection = options[{'network': 'networks', 'bridge': 'bridges', 'direct': 'physical'}[kind]]
    selected = next((item for item in collection if item['name'] == source), None)
    if selected is None or (kind == 'network' and not selected['active']):
        raise ValueError('La red o interfaz seleccionada no está disponible; actualizá las opciones.')
    model = payload.get('model')
    if model not in MODELS:
        raise ValueError('Modelo de placa no permitido.')
    mac = str(payload.get('mac', '')).lower()
    if not mac and adding:
        mac = '52:54:00:' + ':'.join(f'{byte:02x}' for byte in secrets.token_bytes(3))
    if not MAC.fullmatch(mac) or int(mac[:2], 16) & 1 or mac == '00:00:00:00:00:00':
        raise ValueError('Ingresá una MAC unicast válida.')
    if any(item is not node and item.find('mac') is not None and item.find('mac').get('address', '').lower() == mac
           for item in devices.findall('interface')):
        raise ValueError('Otra placa de esta VM ya usa esa dirección MAC.')
    link = payload.get('link_state', 'up')
    if link not in {'up', 'down'}:
        raise ValueError('Estado del enlace inválido.')
    mtu = number(payload.get('mtu'), 'MTU', 576, 9000)
    if kind == 'direct' and mtu:
        raise ValueError('El puente directo hereda la MTU de la placa física; dejá este campo vacío.')
    queues = number(payload.get('queues'), 'Colas VirtIO', 1, min(256, int(root.findtext('vcpu', '1'))))
    if queues and model != 'virtio':
        raise ValueError('Las colas múltiples requieren el modelo VirtIO.')
    if mtu and selected.get('mtu') and mtu > selected['mtu']:
        raise ValueError('La MTU no puede superar la de la interfaz del host.')
    old_source = node.find('source')
    old_key = {'network': 'network', 'bridge': 'bridge', 'direct': 'dev'}.get(node.get('type'))
    connection_changed = node.get('type') != kind or old_source is None or old_source.get(old_key) != source
    if connection_changed and any(node.find(tag) is not None for tag in ('virtualport', 'vlan', 'filterref', 'bandwidth', 'port', 'teaming')):
        raise ValueError('Esta placa tiene políticas avanzadas de red. Cambiá su conexión desde el hipervisor para conservarlas.')
    if node.get('type') == 'direct' and not connection_changed and old_source.get('mode', 'vepa') != 'bridge':
        if payload.get('direct_bridge') is not True:
            raise ValueError('Confirmá el cambio a modo puente directo.')
    for tag in ('mac', 'model', 'link', 'mtu'):
        child = node.find(tag)
        if child is not None:
            node.remove(child)
    if connection_changed or kind == 'direct':
        for tag in ('source', 'target', 'actual'):
            child = node.find(tag)
            if child is not None:
                node.remove(child)
        attrs = {'network': {'network': source}, 'bridge': {'bridge': source},
                 'direct': {'dev': source, 'mode': 'bridge'}}[kind]
        ET.SubElement(node, 'source', **attrs)
    node.set('type', kind)
    ET.SubElement(node, 'mac', address=mac)
    ET.SubElement(node, 'model', type=model)
    ET.SubElement(node, 'link', state=link)
    if mtu:
        ET.SubElement(node, 'mtu', size=str(mtu))
    driver = node.find('driver')
    if driver is not None:
        driver.attrib.pop('queues', None)
        if model != 'virtio':
            node.remove(driver)
            driver = None
    if queues:
        if driver is None:
            driver = ET.SubElement(node, 'driver', name='vhost')
        driver.set('queues', str(queues))
    return root
