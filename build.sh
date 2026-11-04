#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests -q
.venv/bin/python tools/build_release.py
