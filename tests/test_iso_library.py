import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch,MagicMock

spec=importlib.util.spec_from_file_location('iso_library',Path(__file__).parents[1]/'scripts/shc_vm_create.py')
module=importlib.util.module_from_spec(spec)
with patch.dict(sys.modules,{'fcntl':MagicMock()}):spec.loader.exec_module(module)


class ISOLibraryTests(unittest.TestCase):
    def test_nested_iso_and_uppercase_extension(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);nested=base/'VM'/'Installer';nested.mkdir(parents=True)
            iso=nested/'Windows.ISO';iso.write_bytes(b'example')
            with patch.object(module,'iso_roots',return_value=[base]):
                self.assertEqual(module.validate_iso(str(iso)),str(iso.resolve()))
                result=module.browse_isos({'path':str(nested)})
            self.assertEqual(result['entries'][0]['kind'],'iso')
            self.assertEqual(result['parent'],str(nested.parent))

    def test_browser_does_not_list_unrelated_files(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);(base/'private.txt').write_text('private');(base/'install.iso').write_bytes(b'iso')
            with patch.object(module,'iso_roots',return_value=[base]):
                result=module.browse_isos({'path':str(base)})
            self.assertEqual([item['name'] for item in result['entries']],['install.iso'])
            self.assertIsNone(result['parent'])

    def test_escape_and_non_iso_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);allowed=base/'allowed';allowed.mkdir();outside=base/'other.iso';outside.write_bytes(b'iso')
            unrelated=allowed/'secret.txt';unrelated.write_text('private')
            with patch.object(module,'iso_roots',return_value=[allowed]):
                with self.assertRaises(ValueError):module.validate_iso(str(outside))
                with self.assertRaises(ValueError):module.validate_iso(str(unrelated))
                with self.assertRaises(ValueError):module.browse_isos({'path':str(allowed/'..')})


if __name__=='__main__':unittest.main()
