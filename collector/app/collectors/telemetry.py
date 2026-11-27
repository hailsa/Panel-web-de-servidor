"""Host measurements with cached hardware and an energy-counter delta."""
from functools import lru_cache
import json
import subprocess
import threading
import time

_lock = threading.Lock()
_previous = None
_power = None


def query(action):
    try:
        result = subprocess.run(['sudo', '-n', '/usr/local/libexec/shc-host-telemetry', action],
                                capture_output=True, text=True, timeout=5, check=True)
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


@lru_cache(maxsize=2)
def inventory(action, period):
    return query(action)


def power():
    global _previous, _power
    with _lock:
        now = time.monotonic()
        if _previous and now - _previous[0] < 1.5:
            return _power
        sample = query('energy') or {}
        watts = None
        if _previous and sample and sample.keys() == _previous[1].keys():
            then, previous = _previous
            watts = round(sum((v[0] - previous[k][0]) % v[1] for k, v in sample.items()
                              if v[1] > 0) / (now - then) / 1_000_000, 1)
        _previous = (now, sample)
        _power = watts
        return watts
