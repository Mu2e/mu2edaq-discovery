#!/usr/bin/env bash
# Create/update venv/ and launch the discovery GUI.
# All arguments are passed through to mu2edaq-discover-gui.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

if [ ! -d venv ]; then
    python3 -m venv venv
fi

venv/bin/python -m pip install --quiet --upgrade pip
venv/bin/python -m pip install --quiet -e '.[gui]'

exec venv/bin/python -m mu2edaq_discovery.gui "$@"
