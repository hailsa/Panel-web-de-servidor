import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('connection', Path(__file__).parents[1] / 'collector/app/collectors/connection.py')
connection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(connection)


class ConnectionTests(unittest.TestCase):
    def test_three_signal_levels_and_exact_interface(self):
        for dbm, bars in [(-42, 3), (-70, 2), (-90, 1)]:
            signal = connection.wifi_signal('wlan1', f'wlan0: 0000 70. -40. -256\nwlan1: 0000 70. {dbm}. -256')
            self.assertEqual(signal['signal_bars'], bars)
            self.assertEqual(signal['signal_dbm'], dbm)

    def test_unavailable_signal_is_not_full_strength(self):
        for content in ['', 'wlan0: 0000 0. 0. 0', 'wlan0: bad', 'wlan0: 0000 70. 214. -256']:
            self.assertIsNone(connection.wifi_signal('wlan0', content))

    def collect(self, rows, wifi=False, physical=False):
        response = SimpleNamespace(returncode=0, stdout=json.dumps(rows))
        with patch.object(connection.subprocess, 'run', return_value=response), \
             patch.object(connection.Path, 'is_dir', return_value=wifi), \
             patch.object(connection.Path, 'exists', autospec=True, side_effect=lambda p: physical and p.name == 'device'), \
             patch.object(connection, '_read', side_effect=lambda p: '1' if str(p).endswith('/type') else 'wlan0: 0000 68. -42. -256'):
            return connection.collect_connection()

    def test_uses_routed_wifi_interface(self):
        data = self.collect([{'dev': 'wlan0'}], wifi=True)
        self.assertEqual(data['type'], 'wifi')
        self.assertEqual(data['signal_bars'], 3)

    def test_physical_ethernet_and_virtual_interface_differ(self):
        self.assertEqual(self.collect([{'dev': 'eth0'}], physical=True)['type'], 'ethernet')
        self.assertEqual(self.collect([{'dev': 'tun0'}])['type'], 'other')

    def test_no_route_and_missing_tool(self):
        self.assertEqual(self.collect([])['type'], 'disconnected')
        with patch.object(connection.subprocess, 'run', side_effect=FileNotFoundError):
            self.assertEqual(connection.collect_connection()['type'], 'unknown')

    def test_ipv6_fallback(self):
        with patch.object(connection.subprocess, 'run', side_effect=[SimpleNamespace(returncode=2, stdout=''), SimpleNamespace(returncode=0, stdout='[{"dev":"eth0"}]')]), \
             patch.object(connection.Path, 'is_dir', return_value=False), \
             patch.object(connection.Path, 'exists', autospec=True, side_effect=lambda p: p.name == 'device'), \
             patch.object(connection, '_read', return_value='1'):
            self.assertEqual(connection.collect_connection()['type'], 'ethernet')


if __name__ == '__main__':
    unittest.main()
