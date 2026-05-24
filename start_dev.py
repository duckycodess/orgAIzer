"""
start_dev.py -- Start API + Tauri dev in one command.

    python start_dev.py
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PYTHONUNBUFFERED", "1")

# Ensure cargo is on PATH (rustup installs to ~/.cargo/bin)
cargo_bin = Path.home() / ".cargo" / "bin"
if cargo_bin.exists():
    os.environ["PATH"] = str(cargo_bin) + os.pathsep + os.environ.get("PATH", "")


def wait_for_api(timeout: int = 15) -> bool:
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen("http://127.0.0.1:8000/api/watcher/status", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main() -> None:
    api = subprocess.Popen(
        [sys.executable, "main_api.py"],
        cwd=ROOT,
    )
    print("Starting API server…", flush=True)

    if not wait_for_api():
        print("ERROR: API server failed to start", file=sys.stderr)
        api.terminate()
        sys.exit(1)

    print("API ready. Starting Tauri…", flush=True)

    tauri_dir = ROOT / "tauri-app"
    tauri = subprocess.Popen(["npm", "run", "tauri", "--", "dev"], cwd=tauri_dir)

    def shutdown(sig, frame):
        tauri.terminate()
        api.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    tauri.wait()
    api.terminate()


if __name__ == "__main__":
    main()
