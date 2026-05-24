#!/usr/bin/env bash
# Build OrgAIzer as a distributable installer.
# Output: tauri-app/src-tauri/target/release/bundle/
#
# Run from the project root inside WSL (for Linux builds) or from a
# Windows terminal with WSL Python/Rust/Node on PATH (for Windows .exe).

set -e

echo "==> Building Python API binary..."
pyinstaller api-server.spec --distpath tauri-app/src-tauri/binaries --noconfirm

# Tauri expects the sidecar named api-server-<target-triple>[.exe]
TARGET=$(rustc -vV | sed -n 's|host: ||p')
SRC="tauri-app/src-tauri/binaries/api-server"
DST="tauri-app/src-tauri/binaries/api-server-${TARGET}"

if [ -f "${SRC}.exe" ]; then
    mv "${SRC}.exe" "${DST}.exe"
else
    mv "${SRC}" "${DST}"
fi

echo "==> Building Tauri app (frontend + Rust)..."
cd tauri-app
npm run tauri -- build

echo ""
echo "==> Done. Installer in:"
echo "    tauri-app/src-tauri/target/release/bundle/"
