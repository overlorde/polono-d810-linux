#!/usr/bin/env bash
# Removes the open Polono D810 driver and its queue.
set -euo pipefail

QUEUE="${1:-Polono_D810}"

if [[ $EUID -ne 0 ]]; then
  echo "run with sudo" >&2
  exit 1
fi

lpadmin -x "$QUEUE" 2>/dev/null || true
rm -f /usr/lib/cups/filter/d810-filter
rm -rf /usr/lib/d810 /usr/share/ppd/polono
systemctl restart cups
echo "Polono D810 driver removed."
