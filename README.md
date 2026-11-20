<img width="760" alt="adblockr-4x3" src="https://github.com/user-attachments/assets/824b1d46-b5af-407c-9839-fc7b34875075" />

# adBlockr

adBlockr blocks ads for every device on your Wi-Fi. It runs on a **NM-CYD-C5**, a small ESP32-C5 board with a 2.8" touchscreen.

Set your router's DNS to the board. Ad and tracker sites are blocked. Everything else works as normal.

It runs **MicroPython v1.29.0**.

| | |
|---|---|
| Blocks | About 76,000 ad and tracker domains. You can add your own lists. |
| Speed | Blocked sites answer in about 14 ms. Other sites in about 50 ms. |
| Restart | Blocking starts again about 12 seconds after power-up. |
| Screen | Live count, last-hour graph and settings. |
| Web page | `http://adblockr.local`: stats, top blocked sites, recent lookups, lists and settings. |

## Folder structure

| Path | What it is |
|---|---|
| `adBlockr/` | The app. It is copied to the board as-is. `main.py` starts it. |
| `adBlockr/www/` | The web pages. |
| `adBlockr/fonts/` | The screen fonts (Inter). |
| `bin/` | The official MicroPython firmware for the board. |
| `tools/deploy.sh` | Puts MicroPython and the app on the board over USB. |
| `tools/make_fonts.py` | Rebuilds the fonts. Needs Pillow. |
| `tests/test_logic.py` | Tests you run on your computer. |

## Installation

You need Python 3 and a USB-C cable. The script installs the other tools it needs.

```bash
git clone <this repo> && cd <this repo>
tools/deploy.sh --install        # erases the board, then installs everything
```

1. Tap the three targets on the screen. This sets up the touchscreen.
2. On your phone, join the Wi-Fi **adBlockr-Setup**. The setup page opens. If it doesn't, go to `http://192.168.4.1`.
3. Pick your Wi-Fi and enter its password. Choose an admin password with 8 or more characters. The username is `admin`. You can change both later. The board then restarts.
4. The board downloads the blocklist. This takes about two minutes.
5. On your router, give the board a fixed IP address. Then set the router's DNS server to that IP. The IP is on the home screen.

## Update

```bash
tools/deploy.sh
```

Your settings, lists and touch setup are kept.

## Use

| Button | What it does |
|---|---|
| ⏸ / ▶ | Pause blocking for 5 minutes, or resume. |
| ↻ | Download the lists now. |
| ⚙ | Settings: brightness, screen dimming, Wi-Fi, touch setup, admin login, device info, restart ⏻ and reset 🗑. |

**Reset** erases everything and opens the setup Wi-Fi again.

If taps land in the wrong place, redo the touch setup in Settings. You can also hold the screen while it starts up.

The web page `http://adblockr.local` has the same controls. It also lets you edit the lists, the allowlist, the DNS servers and the time zone.

## Blocklist

The board uses this list by default:

| List | URL | Domains |
|---|---|---|
| [StevenBlack unified hosts](https://github.com/StevenBlack/hosts) (ads + malware, MIT) | `https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts` | 76,103 (20 Nov 2026) |

The list updates every 24 hours.

To add or change lists, open the web **Settings** page and edit *Blocklist URLs*. Put one URL per line.

Use the *Allowlist* to unblock a site. Use the *Custom blocklist* to block one more. Both win over the lists.

The home screen shows the current count next to **List**.

## Development

```bash
python3 tests/test_logic.py                          # run the tests
pip install mpy-cross==1.29.0.post2
for f in adBlockr/*.py; do mpy-cross -march=rv32imc -o /tmp/x.mpy "$f"; done   # check the code compiles
mpremote connect /dev/cu.usbmodem* repl              # Ctrl-C stops the app, Ctrl-D restarts it
```

## Limits

- It only works with IPv4.
- It only answers devices on your own network.
- Some devices skip your DNS, for example browsers with "secure DNS" or iCloud Private Relay. Ads are not blocked on those.
- Lists are downloaded without checking the server's certificate. A fake list could only change what gets blocked.
- The touchscreen check is tuned for the ESP32-C5. If that fails, touch still works but the board answers lookups more slowly.

## Licences

- Inter font: SIL Open Font License 1.1 (`adBlockr/fonts/OFL-Inter.txt`).
- MicroPython: MIT.
