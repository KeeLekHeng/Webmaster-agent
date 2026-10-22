#!/bin/bash
set -euo pipefail
export PIP_NO_CACHE_DIR=1
cd /opt/guardian/app
python3 -m venv --without-pip .venv
pip_wheel=(/opt/guardian/wheelhouse/pip-*.whl)
test "${#pip_wheel[@]}" -eq 1
PYTHONPATH="${pip_wheel[0]}" .venv/bin/python -m pip install --no-index --no-deps --find-links=/opt/guardian/wheelhouse pip setuptools wheel
.venv/bin/python -m pip install --no-index --no-deps --find-links=/opt/guardian/wheelhouse -r requirements-dev.lock
.venv/bin/python -m pip install --no-index --no-build-isolation --no-deps .
.venv/bin/python -m pip check
