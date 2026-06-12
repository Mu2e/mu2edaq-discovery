#!/usr/bin/env bash
# Bootstrap mu2edaq-discovery: create venv, install package + dev deps.
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
venv/bin/pip install --upgrade pip >/dev/null
venv/bin/pip install -e '.[dev,yaml]'

echo "Done. Activate with: source venv/bin/activate"
echo "Run tests with:      venv/bin/pytest"
