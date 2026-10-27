import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('journal_helper',Path(__file__).parents[1]/'scripts/shc-journal-helper.py')
helper=importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class JournalTests(unittest.TestCase):
    def test_only_read_actions(self):
        with patch.object(helper,'run') as run:
            with self.assertRaises(ValueError):helper.handle({'action':'vacuum'})
            run.assert_not_called()

    def test_filters_are_not_cli_options(self):
        args,*_=helper.command({'identifier':'--vacuum-size=1M','search':'.*'})
        self.assertIn('SYSLOG_IDENTIFIER=--vacuum-size=1M',args)
        self.assertNotIn('--vacuum-size=1M',args)
        for value in ['*','../x','x\n--vacuum','--unit=*']:
            with self.assertRaises(ValueError):helper.command({'unit':value})

    def test_date_and_page_bounds(self):
        for request in [{'limit':10000},{'priority':9},{'cursor':'abc\n--vacuum'},
                        {'range':'custom','since':'2026-01-01T00:00:00Z','until':'2026-10-01T00:00:00Z'}]:
            with self.assertRaises(ValueError):helper.command(request)

    def test_cursor_excludes_anchor_without_losing_same_timestamp(self):
        events=[{'__CURSOR':f's={number}','__REALTIME_TIMESTAMP':'1','MESSAGE':'hello'} for number in range(22)]
        with patch.object(helper,'run',return_value='\n'.join(json.dumps(event) for event in events)):
            result=helper.query({'limit':20,'cursor':'s=0','range':'boot'})
        self.assertEqual([item['__CURSOR'] for item in result['entries']],[f's={number}' for number in range(1,21)])
        self.assertTrue(result['has_more'])
        self.assertEqual(result['next_cursor'],'s=20')

    def test_search_is_literal_not_regex(self):
        events=[{'__CURSOR':'s=1','MESSAGE':'everything'},{'__CURSOR':'s=2','MESSAGE':'literal .* token'}]
        with patch.object(helper,'run',return_value='\n'.join(json.dumps(event) for event in events)):
            result=helper.query({'search':'.*','range':'boot'})
        self.assertEqual(len(result['entries']),1)
        self.assertEqual(result['entries'][0]['__CURSOR'],'s=2')

    def test_sensitive_unselected_fields_are_excluded(self):
        result=helper.normalize({'MESSAGE':'ok','_CMDLINE':'secret value','SOMETHING':'private'})
        self.assertNotIn('_CMDLINE',result)
        self.assertNotIn('private',str(result))

    def test_cursor_date_bound_is_applied_without_incompatible_cli_flags(self):
        payload={'range':'custom','since':'2026-01-01T00:00:00Z','until':'2026-01-02T00:00:00Z','cursor':'s=1'}
        args,*_=helper.command(payload)
        self.assertFalse(any(arg.startswith('--since=') for arg in args))
        events=[{'__CURSOR':'s=1','__REALTIME_TIMESTAMP':'1767268800000000','MESSAGE':'anchor'},
                {'__CURSOR':'s=2','__REALTIME_TIMESTAMP':'1','MESSAGE':'out of range'}]
        with patch.object(helper,'run',return_value='\n'.join(json.dumps(event) for event in events)):
            result=helper.query(payload)
        self.assertFalse(result['has_more'])
        self.assertEqual(result['entries'],[])


if __name__=='__main__':unittest.main()
