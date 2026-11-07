"""Update policy and worker safeguards without installing any packages."""
import contextlib
import importlib.util
import json
import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch, Mock

SPEC=importlib.util.spec_from_file_location('shc_updates',Path(__file__).parents[1]/'scripts/shc_updates.py')
updates=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(updates)


class UpdatePolicy(unittest.TestCase):
    def test_streaming_feed_keeps_only_requested_sources_and_handles_escaped_braces(self):
        raw=json.dumps({'ignored':{'CVE-2026-1111':{'description':'ignore'}},'sample':{'CVE-2026-2222':{'description':'escapes: \\" { [ ] } y ñ'}}},ensure_ascii=False).encode()
        result={}
        class SmallChunks(io.BytesIO):
            def read(self,size=-1):return super().read(min(size,7))
        updates.stream_tracker(SmallChunks(raw),{'sample'},lambda key,value:result.update({key:value}))
        self.assertEqual(list(result),['sample']);self.assertIn('ñ',result['sample']['CVE-2026-2222']['description'])
        for invalid in [raw[:-5],b'[]']:
            with self.assertRaises(ValueError):updates.stream_tracker(io.BytesIO(invalid),{'sample'},lambda *_:None)
        with self.assertRaises(ValueError):updates.stream_tracker(io.BytesIO(raw),{'sample'},lambda *_:None,maximum=10)

    def test_security_cve_must_affect_installed_version_and_be_fixed_by_candidate(self):
        row={'debian':True,'source_package':'sample','installed_source_version':'2','candidate_source_version':'4'}
        tracker={'sample':{'CVE-2026-10001':{'releases':{'trixie':{'status':'resolved','fixed_version':'3','urgency':'high'}}},
                           'CVE-2026-10002':{'releases':{'trixie':{'status':'resolved','fixed_version':'1','urgency':'high'}}},
                           'CVE-2026-10003':{'releases':{'trixie':{'status':'open','urgency':'medium'}}}}}
        compare=lambda a,b:(int(a)>int(b))-(int(a)<int(b))
        result=updates.cves_for(row,tracker,'trixie',compare)
        self.assertEqual([c['id'] for c in result],['CVE-2026-10001','CVE-2026-10003'])
        self.assertTrue(result[0]['fixed_by_candidate']);self.assertFalse(result[1]['fixed_by_candidate'])
        self.assertEqual(updates.cves_for(dict(row,debian=False),tracker,'trixie',compare),[])

    def test_apt_simulation_must_match_exact_reviewed_versions(self):
        changes=[{'id':'sample:amd64','candidate':'2:3.0-1'},{'id':'dependency:all','candidate':'4'}]
        text='Inst sample [2.0] (2:3.0-1 Debian:stable [amd64])\nInst dependency (4 Debian:stable [all])\n'
        updates.validate_simulation(text,changes)
        for invalid in [text+'Remv essential [1]\n',text+'Inst surprise (1 Debian [amd64])\n',text.replace('2:3.0-1','2:3.0-2'),text.splitlines()[0]]:
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):updates.validate_simulation(invalid,changes)

    def test_install_command_cannot_remove_downgrade_or_ignore_trust(self):
        args=updates.install_command({'changes':[{'id':'sample:amd64','candidate':'1:2.0-1'}]})
        self.assertIn('--no-remove',args);self.assertIn('sample:amd64=1:2.0-1',args)
        for flag in ['--force-yes','--allow-unauthenticated','--allow-downgrades','--allow-change-held-packages','autoremove','dist-upgrade']:
            self.assertNotIn(flag,args)

    def test_apply_requires_confirmation_acknowledgement_and_unexpired_plan(self):
        with patch.object(updates,'queue_job') as queue:
            for body in [{'action':'apply'},{'action':'apply','confirm':True},{'action':'apply','confirm':True,'acknowledge':True,'plan_id':'../../file'}]:
                with self.assertRaises((ValueError,TypeError)):updates.handle(body)
            with patch.object(updates,'read',return_value={'expires_at':0,'changes':[{}]}):
                with self.assertRaises(ValueError):updates.handle({'action':'apply','confirm':True,'acknowledge':True,'plan_id':'11111111-1111-1111-1111-111111111111'})
            queue.assert_not_called()

    def test_unknown_actions_and_unlisted_changelog_packages_rejected(self):
        with self.assertRaises(ValueError):updates.handle({'action':'shell','confirm':True})
        with patch.object(updates,'inventory',return_value={'packages':[]}):
            with self.assertRaises(ValueError):updates.handle({'action':'changelog','package':'--bad'})

    def test_logs_redact_repository_credentials_and_tokens(self):
        result=updates.redact('https://user:password@repo.example/index?token=secret&x=1')
        self.assertNotIn('password',result);self.assertNotIn('secret',result);self.assertIn('repo.example',result)

    def test_worker_revalidates_before_any_package_install(self):
        job_id='11111111-1111-1111-1111-111111111111'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'jobs').mkdir();(root/'backups').mkdir();(root/'plans').mkdir()
            plan={'scope':'security','fingerprint':'old','expires_at':time.time()+600,'changes':[{'id':'sample:amd64','candidate':'2'}]}
            job={'id':job_id,'kind':'install','state':'queued','plan_id':job_id}
            updates.write(root/'plans'/f'{job_id}.json',plan)
            updates.write(root/'jobs'/f'{job_id}.json',job)
            with patch.object(updates,'STATE',root),patch.object(updates,'lock',return_value=contextlib.nullcontext()),patch.object(updates,'build_plan',return_value=dict(plan,fingerprint='changed')),patch.object(updates,'scan'),patch.object(updates.subprocess,'run') as execute:
                updates.run_worker(job_id)
                execute.assert_not_called()
            final=updates.read(root/'jobs'/f'{job_id}.json')
            self.assertEqual(final['state'],'failed');self.assertIn('cambiaron',final['error'])
            self.assertEqual(list((root/'backups').iterdir()),[])

    def test_approved_worker_uses_exact_command_and_preserves_plan_backup(self):
        job_id='22222222-2222-2222-2222-222222222222'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for folder in ['jobs','plans','backups']:(root/folder).mkdir()
            plan={'scope':'security','fingerprint':'reviewed','expires_at':time.time()+600,'changes':[{'id':'sample:amd64','candidate':'2'}]}
            updates.write(root/'plans'/f'{job_id}.json',plan)
            updates.write(root/'jobs'/f'{job_id}.json',{'id':job_id,'kind':'install','state':'queued','plan_id':job_id})
            with patch.object(updates,'STATE',root),patch.object(updates,'lock',return_value=contextlib.nullcontext()),patch.object(updates,'build_plan',return_value=plan),patch.object(updates,'scan'),patch.object(updates,'command',return_value='sample\t1\n'),patch.object(updates.tarfile,'open'),patch.object(updates.subprocess,'run',return_value=Mock(returncode=0)) as execute:
                updates.run_worker(job_id)
            final=updates.read(root/'jobs'/f'{job_id}.json')
            self.assertEqual(final['state'],'succeeded')
            self.assertEqual(execute.call_args.args[0],updates.install_command(plan))
            self.assertNotIn('timeout',execute.call_args.kwargs,'DPKG must not be killed by a worker timeout')
            self.assertEqual(updates.read(root/'backups'/job_id/'plan.json')['fingerprint'],'reviewed')


if __name__=='__main__':unittest.main()
