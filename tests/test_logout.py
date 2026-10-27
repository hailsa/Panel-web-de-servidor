"""Regression tests for the browser logout form."""

import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import auth
from app.main import app


class LogoutTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(auth, "DB_PATH", Path(self.directory.name) / "auth.sqlite3")
        self.path_patch.start()
        self.client = TestClient(app, base_url="https://testserver")
        self.client.__enter__()
        auth.set_user("tester", "test-password")
        response = self.client.post(
            "/login", data={"username": "tester", "password": "test-password"}, follow_redirects=False
        )
        self.assertEqual(response.status_code, 303)

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.path_patch.stop()
        self.directory.cleanup()

    def test_logout_without_origin_redirects_and_revokes_session(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        csrf_token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)

        response = self.client.post("/logout", data={"csrf_token": csrf_token}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/login")
        self.assertEqual(self.client.get("/", follow_redirects=False).headers["location"], "/login")

    def test_logout_rejects_missing_csrf_token(self):
        response = self.client.post("/logout", data={}, follow_redirects=False)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_terminal_is_available_on_every_panel_page(self):
        for path in ("/", "/usuarios", "/estado-servidor"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn('id="terminal-toggle"', response.text)
                self.assertIn('id="terminal-panel"', response.text)
                self.assertIn('id="terminal-screen"', response.text)
                self.assertIn('/static/js/terminal.js?v=v0.4.9', response.text)


if __name__ == "__main__":
    unittest.main()
