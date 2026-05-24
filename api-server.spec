# PyInstaller spec — builds the FastAPI API server into a single binary.
# Run with: pyinstaller api-server.spec

import sys
from pathlib import Path

ROOT = Path(".").resolve()

a = Analysis(
    ["main_api.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        ("pretrained", "pretrained"),
        ("storage", "storage"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "sklearn.utils._cython_blas",
        "sklearn.neighbors.typedefs",
        "sklearn.neighbors.quad_tree",
        "sklearn.tree._utils",
        "pdfplumber",
        "pdfminer",
        "docx",
        "pptx",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["PySide6", "PyQt5", "tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="api-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    onefile=True,
)
