"""Protect data disks while ejecting live and persistent optical media."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

SPEC=importlib.util.spec_from_file_location('media_helper',Path(__file__).parents[1]/'scripts/shc-vm-helper.py')
helper=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
DOMAIN='11111111-1111-1111-1111-111111111111'
ISO='/var/lib/libvirt/boot/test.iso'
XML=f'<domain><devices><disk type="file" device="disk"><source file="/data/test.qcow2"/><target dev="vda"/></disk><disk type="file" device="cdrom"><source file="{ISO}"/><target dev="sdb"/><readonly/></disk></devices></domain>'
EMPTY=XML.replace(f'<source file="{ISO}"/>','')


class Media(unittest.TestCase):
    def request(self,**changes):
        return {'target':'sdb','expected_source':ISO,'expected_persistent_source':ISO,**changes}

    def command(self,empty_after=True,locked=False):
        changed=[]
        def virsh(*args,**kwargs):
            if args[0]=='dominfo':return 'Persistent: yes'
            if args[0]=='dumpxml':return EMPTY if changed and empty_after else XML
            if args[0]=='change-media':
                changed.append(args)
                if locked:raise ValueError('tray locked')
                return ''
            raise AssertionError(args)
        return virsh,changed

    def test_running_ejects_live_and_config_without_force(self):
        command,changed=self.command()
        with patch.object(helper,'virsh',side_effect=command),patch.object(helper,'xml_for',return_value=ET.fromstring(EMPTY)),patch.object(helper,'backup_config') as backup:
            helper.eject_media(DOMAIN,ET.fromstring(XML),'running',self.request())
            self.assertEqual(changed,[('change-media','--domain',DOMAIN,'--path','sdb','--eject','--live','--config')])
            backup.assert_called_once_with(DOMAIN,XML)

    def test_offline_uses_config_only(self):
        command,changed=self.command()
        with patch.object(helper,'virsh',side_effect=command),patch.object(helper,'backup_config'):
            helper.eject_media(DOMAIN,ET.fromstring(XML),'shut off',self.request())
        self.assertIn('--config',changed[0]);self.assertNotIn('--live',changed[0])

    def test_data_disks_missing_targets_and_changed_media_are_rejected(self):
        for request in (self.request(target='vda'),self.request(target='sdc'),self.request(target='--other'),self.request(expected_source='/other.iso'),self.request(expected_persistent_source='')):
            command,changed=self.command()
            with self.subTest(request=request),patch.object(helper,'virsh',side_effect=command),patch.object(helper,'backup_config') as backup:
                with self.assertRaises(ValueError):helper.eject_media(DOMAIN,ET.fromstring(XML),'running',request)
                self.assertEqual(changed,[]);backup.assert_not_called()

    def test_locked_guest_reports_failure_without_forced_retry(self):
        command,changed=self.command(locked=True)
        with patch.object(helper,'virsh',side_effect=command),patch.object(helper,'backup_config'):
            with self.assertRaisesRegex(ValueError,'apagá la VM'):helper.eject_media(DOMAIN,ET.fromstring(XML),'running',self.request())
        self.assertEqual(len(changed),1);self.assertNotIn('--force',changed[0])

    def test_success_is_not_claimed_when_media_remains(self):
        command,_=self.command(empty_after=False)
        with patch.object(helper,'virsh',side_effect=command),patch.object(helper,'xml_for',return_value=ET.fromstring(XML)),patch.object(helper,'backup_config'):
            with self.assertRaisesRegex(ValueError,'todavía no liberó'):helper.eject_media(DOMAIN,ET.fromstring(XML),'running',self.request())

    def test_empty_live_drive_can_clear_media_saved_for_next_boot(self):
        command,changed=self.command()
        with patch.object(helper,'virsh',side_effect=command),patch.object(helper,'backup_config'):
            helper.eject_media(DOMAIN,ET.fromstring(EMPTY),'running',self.request(expected_source=''))
        self.assertNotIn('--live',changed[0]);self.assertIn('--config',changed[0])


if __name__=='__main__':unittest.main()
