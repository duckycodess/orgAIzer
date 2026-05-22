"""
main.py -- OrgAIzer application entry point.

Sets up:
  - Python logging
  - sys.path for module resolution
  - QApplication
  - MainWindow

Run with:
    python main.py
"""

import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path when running from any working directory.
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui.main_window import MainWindow
from ui.theme import load_stylesheet


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    _configure_logging()

    app = QApplication(sys.argv)
    app.setStyleSheet(load_stylesheet())
    app.setApplicationName("OrgAIzer")
    app.setApplicationDisplayName("OrgAIzer")
    app.setOrganizationName("CS180")

    # Keep the app alive when the last window is closed (tray mode).
    app.setQuitOnLastWindowClosed(False)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
