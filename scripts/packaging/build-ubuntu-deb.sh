#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip
python -m pip install -e . build
python -m build

echo "Debian packaging metadata lives in packaging/ubuntu/debian/."
echo "Install dpkg-buildpackage/debhelper and extend this script when the .deb recipe is finalized."
