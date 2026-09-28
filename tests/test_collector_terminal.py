"""Regression test for repeated collector terminal connections."""

import json
import os
import asyncio
import unittest
from pathlib import Path

import websockets


@unittest.skipUnless(os.path.isdir("/home/hailsa"), "Requires the Debian shell account")
class CollectorTerminalTests(unittest.TestCase):
    def test_repeated_terminal_sessions_return_output(self):
        token = Path("/etc/shc-monitor/collector-token").read_text(encoding="utf-8").strip()

        async def check_one(number: int) -> None:
            async with websockets.unix_connect(
                    "/run/shc-monitor/collector.sock",
                    uri="ws://collector/v1/terminal",
                    additional_headers={"Authorization": f"Bearer {token}"},
            ) as websocket:
                marker = f"{1000 + number}\r\n"
                await websocket.send(json.dumps({"type": "input", "data": f"echo $(({1000 + number}))\n"}))
                output = ""
                for _ in range(100):
                    try:
                        output += await asyncio.wait_for(websocket.recv(), timeout=5)
                    except TimeoutError:
                        self.fail(f"session {number} stalled after {len(output)} bytes: {output[:160]!r}")
                    if marker in output:
                        break
                self.assertIn(marker, output, f"session {number} did not return command output")

        async def check() -> None:
            for number in range(12):
                await check_one(number)
            await asyncio.gather(*(check_one(100 + number) for number in range(3)))

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
