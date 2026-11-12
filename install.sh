#!/usr/bin/env bash
# Installs the open Polono D810 driver into CUPS and creates a print queue.
#   sudo ./install.sh            -> queue named "Polono_D810"
#   sudo ./install.sh MyName     -> custom queue name
set -euo pipefail

QUEUE="${1:-Polono_D810}"
HERE="$(cd "$(dirname "$0")" && pwd)"
LIB_DIR=/usr/lib/d810
FILTER_DIR=/usr/lib/cups/filter
PPD_DIR=/usr/share/ppd/polono

if [[ $EUID -ne 0 ]]; then
  echo "run with sudo" >&2
  exit 1
fi

echo "== checking dependencies"
missing=()
command -v gs >/dev/null || missing+=(ghostscript)
/usr/bin/python3 -c "import PIL" 2>/dev/null || missing+=(python3-pil)
if (( ${#missing[@]} )); then
  apt-get install -y "${missing[@]}"
fi

echo "== copying files"
install -d "$LIB_DIR" "$PPD_DIR"
install -m 644 "$HERE/d810.py" "$LIB_DIR/d810.py"
install -m 755 "$HERE/cups/d810-filter" "$FILTER_DIR/d810-filter"
install -m 644 "$HERE/ppd/polono-d810.ppd" "$PPD_DIR/polono-d810.ppd"

echo "== finding the printer"
# The usb backend prints something like: direct usb:///D810?serial=XXXX "D810" ...
URI="$(/usr/lib/cups/backend/usb 2>/dev/null | awk '/D810/ {print $2; exit}')"
if [[ -z "$URI" ]]; then
  # Printer is off or busy; fall back to the first queue that already points at it.
  URI="$(lpstat -v 2>/dev/null | awk '/D810/ {print $NF; exit}')"
fi
if [[ -z "$URI" ]]; then
  echo "D810 not found on USB. Turn it on, plug it in, and run this again." >&2
  exit 1
fi
echo "   $URI"

echo "== creating queue $QUEUE"
systemctl restart cups
lpadmin -x "$QUEUE" 2>/dev/null || true
lpadmin -p "$QUEUE" -E -v "$URI" -P "$PPD_DIR/polono-d810.ppd" \
        -D "Polono D810" -L "USB" -o printer-is-shared=false

echo
echo "Done. Print with:  lp -d $QUEUE file.pdf"
echo "Options:  -o PageSize=Letter  -o MediaType=Roll  -o Darkness=Medium"
