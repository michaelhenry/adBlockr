# Persistent settings (/settings.json) and small text-file helpers.
import json
import os
from config import *

DEFAULTS = {
    "ssid": "", "pw": "",                  # Wi-Fi
    "ip": "", "gw": "", "mask": "",        # static IP (empty = DHCP)
    "auser": "admin", "apass": "",         # web admin (HTTP basic auth)
    "up1": DEFAULT_UPSTREAM1, "up2": DEFAULT_UPSTREAM2,
    "local": True,                         # *.lan, single-label, private PTR -> router
    "subdom": False,                       # also block subdomains of listed domains
    "bright": 200, "dim": SCREEN_DIM_DEFAULT_S,
    "tz": DEFAULT_TZ,
    "tcal": None,                          # touch calibration, see ui.calibrate()
}

s = dict(DEFAULTS)


def load():
    try:
        with open(SETTINGS_FILE) as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass


def save():
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f)
    os.rename(tmp, SETTINGS_FILE)          # never leaves a half-written settings file


def clear_wifi():
    s["ssid"] = s["pw"] = ""
    save()


def factory_reset():
    for p in (SETTINGS_FILE, LISTS_FILE, ALLOW_FILE, BLOCK_FILE, CACHE_FILE):
        try:
            os.remove(p)
        except OSError:
            pass


def read_text(path, dflt=""):
    try:
        with open(path) as f:
            return f.read()
    except OSError:
        return dflt


def write_text(path, text):
    with open(path, "w") as f:
        f.write(text)
