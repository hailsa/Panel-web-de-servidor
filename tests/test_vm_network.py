"""NIC editing and IP discovery must not mutate a running VM or host networking."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import shc_vm_network as network

SPEC = importlib.util.spec_from_file_location('network_vm_helper', Path(__file__).parents[1] / 'scripts/shc-vm-helper.py')
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
DOMAIN = '11111111-1111-1111-1111-111111111111'
XML = f'''<domain type="kvm"><name>test</name><uuid>{DOMAIN}</uuid><vcpu>4</vcpu><devices>
<disk type="file"><source file="/tmp/unchanged.qcow2"/></disk>
<interface type="network"><mac address="52:54:00:11:22:33"/><source network="default"/>
<model type="e1000e"/><address type="pci" slot="0x01"/></interface></devices></domain>'''
OPTIONS = {'networks': [{'name': 'default', 'active': True}, {'name': 'inactive', 'active': False}],
           'bridges': [{'name': 'brlan', 'mtu': 1500}], 'physical': [{'name': 'eth0', 'mtu': 1500}]}


class NetworkControls(unittest.TestCase):
    def payload(self, **changes):
        return {'action': 'network-edit', 'interface_mac': '52:54:00:11:22:33', 'network_type': 'direct',
                'source': 'eth0', 'mac': '52:54:00:11:22:33', 'model': 'e1000e', 'link_state': 'up', **changes}

    def test_switch_to_lan_preserves_other_devices_and_pci_slot(self):
        root = ET.fromstring(XML)
        result = network.configure_interface(root, self.payload(), OPTIONS)
        nic = result.find('devices/interface')
        self.assertEqual(nic.get('type'), 'direct')
        self.assertEqual(nic.find('source').attrib, {'dev': 'eth0', 'mode': 'bridge'})
        self.assertEqual(nic.find('address').get('slot'), '0x01')
        self.assertEqual(result.find('devices/disk/source').get('file'), '/tmp/unchanged.qcow2')
        self.assertEqual(root.find('devices/interface').get('type'), 'network')

    def test_bridge_and_virtio_configuration(self):
        result = network.configure_interface(ET.fromstring(XML), self.payload(network_type='bridge', source='brlan', model='virtio', queues='4', mtu='1500', link_state='down'), OPTIONS)
        nic = result.find('devices/interface')
        self.assertEqual(nic.find('source').attrib, {'bridge': 'brlan'})
        self.assertEqual(nic.find('driver').get('queues'), '4')
        self.assertEqual(nic.find('link').get('state'), 'down')

    def test_direct_interface_inherits_host_mtu(self):
        with self.assertRaisesRegex(ValueError, 'hereda la MTU'):
            network.configure_interface(ET.fromstring(XML), self.payload(mtu='1500'), OPTIONS)

    def test_reject_invalid_or_unavailable_values(self):
        for changes in ({'source': '../../etc'}, {'network_type': 'ethernet'}, {'model': 'arbitrary'},
                        {'mac': 'ff:ff:ff:ff:ff:ff'}, {'mac': '00:00:00:00:00:00'},
                        {'link_state': 'invalid'}, {'mtu': '9000'}, {'mtu': '-1'},
                        {'queues': '2'}, {'model': 'virtio', 'queues': '5'},
                        {'network_type': 'network', 'source': 'inactive'}, {'interface_mac': '52:54:00:11:22:44'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                network.configure_interface(ET.fromstring(XML), self.payload(**changes), OPTIONS)

    def test_advanced_policies_cannot_be_dropped_by_switching_connection(self):
        root = ET.fromstring(XML)
        ET.SubElement(root.find('devices/interface'), 'filterref', filter='clean-traffic')
        with self.assertRaises(ValueError):
            network.configure_interface(root, self.payload(), OPTIONS)

    def test_add_interface_and_duplicate_mac(self):
        result = network.configure_interface(ET.fromstring(XML), self.payload(action='network-add', mac=''), OPTIONS)
        mac = result.findall('devices/interface')[1].find('mac').get('address')
        self.assertTrue(mac.startswith('52:54:00:'))
        with self.assertRaises(ValueError):
            network.configure_interface(ET.fromstring(XML), self.payload(action='network-add'), OPTIONS)

    def test_running_vm_is_rejected_before_config_writes(self):
        with patch.object(helper, 'xml_for', return_value=ET.fromstring(XML)), patch.object(helper, 'virsh', return_value='running'), patch.object(helper, 'save_config') as save:
            with self.assertRaises(ValueError):
                helper.handle({'action': 'network-edit', 'id': DOMAIN, 'confirm': True})
            save.assert_not_called()

    def test_full_ipv4_ipv6_addresses_and_arp_deduplication(self):
        text = '''Name MAC Protocol Address
---
eth0 52:54:00:11:22:33 ipv4 192.0.2.24/24
eth0 52:54:00:11:22:33 ipv6 2001:db8::24/64
lo 00:00:00:00:00:01 ipv4 127.0.0.1/8
eth0 52:54:00:11:22:33 ipv4 malformed
'''
        addresses = network.parse_addresses(text, 'agent')
        self.assertEqual(len(addresses), 2)
        nic = network.interface_details(ET.fromstring(XML).find('devices/interface'), addresses + network.parse_addresses(text, 'arp'))
        self.assertEqual(len(nic['addresses']), 2)
        self.assertTrue(all(item['source'] == 'agent' for item in nic['addresses']))

    def test_host_options_exclude_docker_nat_and_wifi_from_bridges(self):
        def virsh(*args):
            if args[0] == 'net-list': return DOMAIN
            if args[0] == 'net-dumpxml': return '<network><name>default</name><forward mode="nat"/><bridge name="virbr0"/></network>'
            return 'Active: yes'
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            for name in ('eth0', 'wifi0', 'brlan', 'virbr0', 'docker0', 'br-abc'):
                path = base / name
                path.mkdir()
                (path / 'operstate').write_text('up')
                (path / 'mtu').write_text('1500')
                if name in {'eth0', 'wifi0'}: (path / 'device').mkdir()
                else:
                    (path / 'bridge').mkdir()
                    (path / 'brif').mkdir()
            (base / 'wifi0/wireless').mkdir()
            options = network.network_options(virsh, base)
            self.assertEqual([item['name'] for item in options['bridges']], ['brlan'])
            self.assertEqual([item['name'] for item in options['physical']], ['eth0'])
            self.assertTrue(options['networks'][0]['active'])


if __name__ == '__main__': unittest.main()
