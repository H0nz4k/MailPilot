#!/usr/bin/env bash
# Full regression suite in its own environment; never adds Qt to the web build.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv-test/Scripts/python.exe"
if [[ ! -f "$PY" ]]; then
  py -3.12 -m venv "$ROOT/.venv-test"
fi
"$PY" -m pip install --disable-pip-version-check -r requirements-test.txt
mkdir -p build/test-results
export QT_QPA_PLATFORM=offscreen
"$PY" -m pytest -q --ignore=test_gui_qt.py --ignore=test_warning_buttons_qt.py --junitxml=build/test-results/regression.xml
