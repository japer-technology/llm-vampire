#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install pyinstaller
pyinstaller packaging/macos/LMStudioVampire.spec
