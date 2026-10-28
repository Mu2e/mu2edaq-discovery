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
# yaml as well as gui: --config (and config/discovery.yaml) needs PyYAML,
# and bootstrap.sh installs it too.
venv/bin/python -m pip install --quiet -e '.[gui,yaml]'

exec venv/bin/python -m mu2edaq_discovery.gui "$@"
