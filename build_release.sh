#!/usr/bin/env bash
# Build OrgAIzer as a distributable installer.
# Output: tauri-app/src-tauri/target/release/bundle/

set -e

echo "==> Building Python API binary..."
pyinstaller api-server.spec --distpath tauri-app/src-tauri/binaries

# Tauri expects sidecar named api-server-<target-triple>
TARGET=$(rustc -vV | sed -n 's|host: ||p')
mv tauri-app/src-tauri/binaries/api-server \
   tauri-app/src-tauri/binaries/api-server-${TARGET}

echo "==> Building Tauri app..."
cd tauri-app
npm run build
cargo tauri build

echo "==> Done. Installer in tauri-app/src-tauri/target/release/bundle/"
