#!/usr/bin/env bash
# Stop the discovery GUI cleanly (TERM, then KILL if it is still up).
set -uo pipefail

pattern='mu2edaq_discovery.gui|mu2edaq-discover-gui'
pids="$(pgrep -f "$pattern" | grep -v "^$$\$" || true)"

if [ -z "$pids" ]; then
    echo "mu2edaq-discover-gui is not running."
    exit 0
fi

echo "Stopping mu2edaq-discover-gui (pids: $pids)"
kill $pids 2>/dev/null

for _ in 1 2 3 4 5; do
    sleep 1
    pids="$(pgrep -f "$pattern" || true)"
    [ -z "$pids" ] && { echo "Stopped."; exit 0; }
done

echo "Still running; sending SIGKILL to: $pids"
kill -9 $pids 2>/dev/null
echo "Stopped."
