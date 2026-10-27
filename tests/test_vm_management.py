"""Validate VM controls without touching a real guest."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

SPEC = importlib.util.spec_from_file_location("vm_helper", Path(__file__).parents[1] / "scripts/shc-vm-helper.py")
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
DOMAIN = "11111111-1111-1111-1111-111111111111"
XML = '<domain><name>test</name><uuid>'+DOMAIN+'</uuid><devices/></domain>'


class VMControls(unittest.TestCase):
    def test_bad_uuid_rejected_before_command(self):
        with patch.object(helper, 'virsh') as virsh:
            with self.assertRaises(ValueError): helper.handle({'action':'start','id':'--other-option','confirm':True})
            virsh.assert_not_called()

    def test_confirmation_required(self):
        with patch.object(helper, 'xml_for', return_value=helper.ET.fromstring(XML)), patch.object(helper, 'virsh') as virsh:
            with self.assertRaises(ValueError): helper.handle({'action':'start','id':DOMAIN})
            virsh.assert_not_called()

    @patch.dict('sys.modules', {'syslog': MagicMock()})
    def test_start_only_when_off(self):
        with patch.object(helper, 'xml_for', return_value=helper.ET.fromstring(XML)), patch.object(helper, 'virsh', return_value='running') as virsh:
            with self.assertRaises(ValueError): helper.handle({'action':'start','id':DOMAIN,'confirm':True})
            self.assertEqual(virsh.call_count,1)
        with patch.object(helper, 'xml_for', return_value=helper.ET.fromstring(XML)), patch.object(helper, 'virsh', return_value='shut off') as virsh:
            self.assertTrue(helper.handle({'action':'start','id':DOMAIN,'confirm':True})['accepted'])
            self.assertEqual(virsh.call_args.args,('start','--domain',DOMAIN))

    def test_snapshot_rejected_while_running(self):
        with patch.object(helper, 'xml_for', return_value=helper.ET.fromstring(XML)), patch.object(helper, 'virsh', return_value='running') as virsh:
            with self.assertRaises(ValueError): helper.handle({'action':'snapshot-create','id':DOMAIN,'name':'safe','confirm':True})
            self.assertEqual(virsh.call_count,1)

    def test_console_cannot_proxy_arbitrary_address(self):
        root=helper.ET.fromstring(XML)
        helper.ET.SubElement(root.find('devices'),'graphics',type='vnc',port='5900',listen='192.0.2.10')
        with patch.object(helper,'xml_for',return_value=root):
            with self.assertRaises(ValueError): helper.handle({'action':'console','id':DOMAIN})

    def test_path_and_option_names_rejected(self):
        for name in ('../../etc','--delete','a/b',''):
            with self.assertRaises(ValueError): helper.safe_name(name)


if __name__=='__main__': unittest.main()
