#!/usr/bin/env bash
# Bootstrap mu2edaq-discovery: create venv, install package + dev deps.
# Pass --gui to also install the Qt binding needed by mu2edaq-discover-gui.
set -euo pipefail

cd "$(dirname "$0")"

extras="dev,yaml"
for arg in "$@"; do
  case "$arg" in
    --gui) extras="$extras,gui" ;;
    -h|--help) echo "usage: $0 [--gui]"; exit 0 ;;
    *) echo "unknown option: $arg (usage: $0 [--gui])" >&2; exit 2 ;;
  esac
done

if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
venv/bin/pip install --upgrade pip >/dev/null
venv/bin/pip install -e ".[$extras]"

echo "Done. Activate with: source venv/bin/activate"
echo "Run tests with:      venv/bin/pytest"
echo "Run the GUI with:    ./start-mu2edaq-discover-gui.sh"
