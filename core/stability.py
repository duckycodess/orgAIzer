"""
core/stability.py -- File stability detection.

A newly created file in Downloads may still be downloading (Chrome, Edge, etc.).
We wait until the file size is stable across multiple checks AND we can open it
for reading before declaring it safe to process.

Also filters out browser temporary download extensions right away.
"""

import time
from pathlib import Path

# Extensions that mean "still downloading" -- skip immediately on on_created,
# but process the on_moved event when the browser renames to the real extension.
TRANSIENT_EXTENSIONS = {".crdownload", ".part", ".tmp", ".download"}

# Stability parameters
_POLL_INTERVAL_S = 1.0      # seconds between size checks
_STABLE_ROUNDS = 3          # number of consecutive same-size reads needed
_TIMEOUT_S = 30.0           # give up after this many seconds


def is_transient(path: str) -> bool:
    """Return True if the file extension signals it's still downloading."""
    return Path(path).suffix.lower() in TRANSIENT_EXTENSIONS


def wait_until_stable(
    path: str,
    poll_interval: float = _POLL_INTERVAL_S,
    stable_rounds: int = _STABLE_ROUNDS,
    timeout: float = _TIMEOUT_S,
) -> bool:
    """
    Block until the file at `path` is stable (done writing).

    Returns True if the file became stable within the timeout.
    Returns False if the file disappeared or timed out.
    """
    p = Path(path)
    deadline = time.monotonic() + timeout
    last_size = -1
    stable_count = 0

    while time.monotonic() < deadline:
        if not p.exists():
            return False  # file disappeared (e.g. moved by something else)

        try:
            current_size = p.stat().st_size
        except OSError:
            time.sleep(poll_interval)
            continue

        if current_size == last_size:
            stable_count += 1
        else:
            # Size changed — reset the stability counter.
            stable_count = 0
            last_size = current_size

        if stable_count >= stable_rounds:
            # Size is stable — try to confirm the file handle is readable.
            if _can_open(path):
                return True
            # Handle still locked — don't reset the counter, just wait.

        time.sleep(poll_interval)

    return False  # timed out


def _can_open(path: str) -> bool:
    """Try to open the file in binary read mode. Returns False if locked."""
    try:
        with open(path, "rb") as f:
            f.read(1)   # read one byte to confirm it's accessible
        return True
    except OSError:
        return False
