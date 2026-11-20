#!/usr/bin/env bash
# Deploy adBlockr to an NM-CYD-C5 over USB.
#
#   tools/deploy.sh            copy/update the adBlockr app (settings and lists are kept)
#   tools/deploy.sh --install  first install: ERASE the whole flash, write MicroPython, then the app
#
# Options: --port /dev/cu.usbmodemXXXX (default: the first USB serial port found)
# Needs: python3. esptool and mpremote are installed with pip if missing.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
APP="$HERE/adBlockr"
FW="$HERE/bin/ESP32_GENERIC_C5-20260824-v1.29.0.bin"
FW_URL="https://micropython.org/resources/firmware/ESP32_GENERIC_C5-20260824-v1.29.0.bin"
FW_SHA256="24a9d43e2b97b191507b6c23ce6825f79a1b6e3292e51ffe4de2d5240bdc77d0"

INSTALL=0
PORT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --install) INSTALL=1 ;;
    --port) PORT="$2"; shift ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

if [ -z "$PORT" ]; then
  PORT="$(ls /dev/cu.usbmodem* /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -1 || true)"
fi
[ -n "$PORT" ] || { echo "No board found. Connect the CYD by USB-C or pass --port." >&2; exit 1; }
echo "Board: $PORT"

need() { python3 -m "$1" --help >/dev/null 2>&1 || python3 -m pip install --user "$2"; }
need esptool esptool
need mpremote mpremote

if [ "$INSTALL" = 1 ]; then
  if [ ! -f "$FW" ]; then
    mkdir -p "$HERE/bin"
    curl -fL -o "$FW" "$FW_URL"
  fi
  got="$(shasum -a 256 "$FW" 2>/dev/null || sha256sum "$FW")"
  [ "${got%% *}" = "$FW_SHA256" ] || { echo "MicroPython image checksum mismatch: $FW" >&2; exit 1; }
  echo "Erasing flash and writing MicroPython (this wipes everything on the board)..."
  python3 -m esptool --chip esp32c5 --port "$PORT" erase-flash
  python3 -m esptool --chip esp32c5 --port "$PORT" --baud 460800 write-flash 0x2000 "$FW"
  sleep 4                                   # first boot formats the filesystem
fi

echo "Copying the adBlockr app..."
MP="python3 -m mpremote connect $PORT"
cd "$APP"
$MP mkdir :fonts >/dev/null 2>&1 || true
$MP mkdir :www >/dev/null 2>&1 || true
$MP cp $(ls *.py | grep -v '^main.py$') :
$MP cp fonts/*.fnt :fonts/
$MP cp www/* :www/
$MP cp main.py :                            # last, so a half-finished copy never boots
echo "Restarting the board..."
$MP reset
echo "Done. Watch the screen; on first install join the 'adBlockr-Setup' Wi-Fi to configure it."
