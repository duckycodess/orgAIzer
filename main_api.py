"""
main_api.py -- Launch the OrgAIzer FastAPI backend.

Run backend only:
    python main_api.py

Then in tauri-app/:
    npm install
    cargo tauri dev     (needs webkit2gtk: sudo apt install libwebkit2gtk-4.1-dev)
"""

import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


if __name__ == "__main__":
    _configure_logging()
    import uvicorn
    uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=True)
