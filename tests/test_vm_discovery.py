"""Static guest IP discovery using synthetic headers, never real traffic."""
import ipaddress
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import shc_vm_discovery as discovery
import shc_vm_network as network

MAC = '52:54:00:11:22:33'
RAW = bytes.fromhex(MAC.replace(':', ''))
OTHER = bytes.fromhex('525400445566')
ROOT = '<domain id="4"><devices><interface type="direct"><mac address="'+MAC+'"/><source dev="eth0" mode="bridge"/></interface></devices></domain>'


def ipv4(source='192.0.2.24', mac=RAW):
    return OTHER + mac + b'\x08\x00' + b'\x45'+bytes(11)+ipaddress.ip_address(source).packed+ipaddress.ip_address('192.0.2.3').packed


class Discovery(unittest.TestCase):
    def test_only_guest_source_mac_is_accepted(self):
        item=discovery.packet_address(ipv4(), {MAC})
        self.assertEqual(item['address'], '192.0.2.24/32')
        self.assertFalse(item['prefix_known'])
        self.assertIsNone(discovery.packet_address(ipv4(mac=OTHER), {MAC}))
        self.assertIsNone(discovery.packet_address(ipv4()[6:12]+OTHER+ipv4()[12:], {MAC}))

    def test_invalid_and_truncated_frames_are_ignored(self):
        for frame in [b'', ipv4()[:20], ipv4('0.0.0.0'), ipv4('127.0.0.1'), ipv4('224.0.0.1'), ipv4('255.255.255.255')]:
            self.assertIsNone(discovery.packet_address(frame, {MAC}))

    def test_arp_sender_must_match_ethernet_mac(self):
        arp=b'\x00\x01\x08\x00\x06\x04\x00\x02'+RAW+ipaddress.ip_address('192.0.2.24').packed+OTHER+ipaddress.ip_address('192.0.2.3').packed
        frame=OTHER+RAW+b'\x08\x06'+arp
        self.assertEqual(discovery.packet_address(frame,{MAC})['family'],4)
        self.assertIsNone(discovery.packet_address(frame[:22]+OTHER+frame[28:],{MAC}))

    def test_vlan_and_ipv6_headers(self):
        tagged=ipv4()[:12]+b'\x81\x00\x00\x01'+ipv4()[12:]
        self.assertEqual(discovery.packet_address(tagged,{MAC})['address'],'192.0.2.24/32')
        frame=OTHER+RAW+b'\x86\xdd'+b'\x60'+bytes(7)+ipaddress.ip_address('2001:db8::24').packed+ipaddress.ip_address('2001:db8::3').packed
        self.assertEqual(discovery.packet_address(frame,{MAC})['address'],'2001:db8::24/128')

    def test_cache_preserves_last_seen_but_expires_and_tracks_instance(self):
        now=int(time.time());item={**discovery.packet_address(ipv4(),{MAC}),'observed_at':now}
        root=ET.fromstring(ROOT)
        with tempfile.TemporaryDirectory() as directory, patch.object(discovery,'sample_headers',return_value=[item]) as sample:
            cache=Path(directory)
            self.assertEqual(discovery.discover_addresses(root,'guest',[],cache),[item])
            sample.return_value=[]
            self.assertEqual(discovery.discover_addresses(root,'guest',[],cache),[item])
            root.set('id','5')
            self.assertEqual(discovery.discover_addresses(root,'guest',[],cache),[])
            sample.return_value=[item]
            discovery.discover_addresses(root,'guest',[],cache)
            sample.return_value=[]
            with patch.object(discovery.time,'time',return_value=now+discovery.RETENTION+1):
                self.assertEqual(discovery.discover_addresses(root,'guest',[],cache),[])

    def test_known_agent_data_prevents_unnecessary_sampling(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(discovery,'sample_headers') as sample:
            discovery.discover_addresses(ET.fromstring(ROOT),'guest',[{'mac':MAC,'source':'agent'}],Path(directory))
            sample.assert_not_called()

    def test_address_deduplication_prefers_agent_prefix(self):
        agent=network.parse_addresses(f'eth0 {MAC} ipv4 192.0.2.24/24','agent')
        observed=discovery.packet_address(ipv4(),{MAC})
        node=ET.fromstring(ROOT).find('devices/interface')
        result=network.interface_details(node,agent+[observed])
        self.assertEqual(len(result['addresses']),1)
        self.assertEqual(result['addresses'][0]['source'],'agent')


if __name__=='__main__':unittest.main()
