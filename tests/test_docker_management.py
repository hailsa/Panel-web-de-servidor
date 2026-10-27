"""Check command boundaries and prevent secret exposure in Docker responses."""
import unittest
from unittest.mock import patch
from fastapi import HTTPException
from collector.app import docker_management as module

ID='a'*64


class DockerManagement(unittest.TestCase):
    def test_invalid_identifier_never_runs_docker(self):
        with patch.object(module,'docker') as command:
            with self.assertRaises(HTTPException):module.detail('--privileged')
            command.assert_not_called()

    def test_confirmation_is_required(self):
        with patch.object(module,'docker') as command:
            with self.assertRaises(HTTPException):module.action(ID,{'action':'stop'})
            command.assert_not_called()

    def test_panel_is_protected(self):
        with patch.object(module,'docker',return_value='[{"Name":"/shc-monitor"}]') as command:
            with self.assertRaises(HTTPException):module.action(ID,{'action':'stop','confirm':True})
            self.assertEqual(command.call_count,1)

    def test_invalid_policy_never_updates(self):
        with patch.object(module,'docker',return_value='[{"Name":"/sample","State":{"Status":"running"}}]') as command:
            with self.assertRaises(HTTPException):module.action(ID,{'action':'restart-policy','policy':'--privileged','confirm':True})
            self.assertEqual(command.call_count,1)

    def test_kill_requires_exact_name(self):
        with patch.object(module,'docker',return_value='[{"Name":"/sample","State":{"Status":"running"}}]') as command:
            with self.assertRaises(HTTPException):module.action(ID,{'action':'kill','verify':'other','confirm':True})
            self.assertEqual(command.call_count,1)

    def test_detail_sends_env_names_only(self):
        raw='[{"Id":"'+ID+'","Name":"/sample","Config":{"Env":["SECRET=private-value"]},"State":{"Status":"exited"}}]'
        with patch.object(module,'docker',return_value=raw), patch.object(module,'stats_map',return_value={}):
            result=module.detail(ID)
            self.assertEqual(result['environment_keys'],['SECRET'])
            self.assertNotIn('private-value',str(result))


if __name__=='__main__':unittest.main()
