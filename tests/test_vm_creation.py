"""VM creation validation must not mutate existing guests or accept host paths."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch,MagicMock

spec=importlib.util.spec_from_file_location('vm_creation',Path(__file__).parents[1]/'scripts/shc_vm_create.py')
module=importlib.util.module_from_spec(spec)
with patch.dict(sys.modules,{'fcntl':MagicMock()}):spec.loader.exec_module(module)

ID='11111111-1111-4111-8111-111111111111'
OPTIONS={'ready':True,'cpus':4,'memory_total_mib':12000,'memory_available_mib':5000,'reserve_mib':1024,
         'pools':[{'id':'pool','name':'default','path':'/var/lib/libvirt/images','free_bytes':200*1073741824}],
         'networks':[{'id':'net','name':'default','mode':'nat'}],
         'isos':[{'path':'/var/lib/libvirt/boot/install.iso'}],'uefi':True,'tpm':True}


def payload(**extra):
    return {'name':'new-vm','request_id':ID,'cpus':2,'memory_mib':2048,'disk_gib':32,'pool':'pool',**extra}


class VMCreationTests(unittest.TestCase):
    def test_windows_uses_emulated_devices_and_does_not_start_by_default(self):
        plan=module.validate(payload(profile='windows'),OPTIONS)
        self.assertEqual(plan['disk_bus'],'sata')
        self.assertEqual(plan['network_model'],'e1000e')
        self.assertFalse(plan['start'])

    def test_host_paths_and_unknown_network_are_rejected(self):
        for values in [{'name':'../etc/passwd'},{'pool':'/tmp'},{'iso':'/etc/shadow'},{'drivers_iso':'/tmp/other.iso'},{'network':'unknown'}]:
            with self.assertRaises(ValueError):module.validate(payload(**values),OPTIONS)

    def test_host_resource_margins(self):
        for values in [{'cpus':99},{'memory_mib':12000},{'disk_gib':200},{'memory_mib':4500,'start':True}]:
            with self.assertRaises(ValueError):module.validate(payload(**values),OPTIONS)

    def test_firmware_dependencies(self):
        with self.assertRaises(ValueError):module.validate(payload(firmware='bios',tpm=True),OPTIONS)
        with self.assertRaises(ValueError):module.validate(payload(firmware='bios',secure_boot=True),OPTIONS)

    def test_preview_cannot_create_storage_or_define_a_guest(self):
        with patch.object(module,'creation_options',return_value=OPTIONS),patch.object(module,'virsh',return_value='') as virsh,patch.object(module,'generate_xml',return_value='<domain/>'),patch.object(module.os.path,'lexists',return_value=False),patch.object(module,'host_memory',return_value={'MemAvailable':5000*1048576}):
            result=module.preview(payload())
            self.assertEqual(result['plan']['name'],'new-vm')
            self.assertTrue(all(call.args[0]=='list' for call in virsh.call_args_list))

    def test_existing_guest_name_and_disk_are_protected(self):
        plan=module.validate(payload(),OPTIONS)
        with patch.object(module,'virsh',return_value='new-vm'):
            with self.assertRaises(ValueError):module.ensure_unused(plan)
        with patch.object(module,'virsh',return_value=''),patch.object(module.os.path,'lexists',return_value=True):
            with self.assertRaises(ValueError):module.ensure_unused(plan)

    def test_creation_requires_confirmation_before_any_changes(self):
        with patch.object(module,'virsh') as virsh:
            with self.assertRaises(ValueError):module.create(payload())
            virsh.assert_not_called()


if __name__=='__main__':unittest.main()
