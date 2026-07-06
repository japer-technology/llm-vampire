$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install pyinstaller
pyinstaller packaging/windows/LMStudioVampire.spec
