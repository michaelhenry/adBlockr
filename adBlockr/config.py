# adBlockr - network-wide DNS ad blocker for the NM-CYD-C5 (ESP32-C5), MicroPython edition.
# Compile-time constants. Runtime settings live in /settings.json and are edited on the
# touchscreen or in the web UI, so you normally do not need to touch this file.

VERSION = "2.0.0"
HOSTNAME = "adblockr"              # mDNS: http://adblockr.local

# NM-CYD-C5 pins (RockBase-lab/NM-CYD-C5)
PIN_SCK, PIN_MOSI, PIN_MISO = 6, 7, 2
PIN_TFT_CS, PIN_TFT_DC = 23, 24    # ST7789 320x240, no reset line
PIN_TOUCH_CS = 1                   # XPT2046 on the same SPI bus
PIN_BL = 25                        # backlight (PWM)
PIN_LED = 27                       # on-board WS2812
SPI_HZ = 20_000_000
TOUCH_HZ = 2_500_000

# ST7789 MADCTL. 0x60 = landscape (USB-C on the right). 0xA0 = upside down;
# after changing it, redo Settings > Calibrate touch.
MADCTL = 0x60

# DNS
DNS_PORT = 53
DEFAULT_UPSTREAM1 = "1.1.1.1"
DEFAULT_UPSTREAM2 = "9.9.9.9"
PENDING_MAX = 64                   # concurrent forwarded queries
UPSTREAM_RETRY_MS = 1000           # retry on the secondary after this
UPSTREAM_TIMEOUT_MS = 2500         # SERVFAIL after this
BLOCKED_TTL = 60

# Blocklist
DEFAULT_LISTS = "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts\n"
LIST_REFRESH_HOURS = 24
CACHE_FILE = "/bl.bin"
LISTS_FILE = "/lists.txt"
ALLOW_FILE = "/allow.txt"
BLOCK_FILE = "/block.txt"
SETTINGS_FILE = "/settings.json"

# Misc
DEFAULT_TZ = "AEST-10AEDT,M10.1.0,M4.1.0/3"   # POSIX TZ (Melbourne)
SETUP_AP_SSID = "adBlockr-Setup"
WIFI_CONNECT_TIMEOUT_MS = 45000
SCREEN_DIM_DEFAULT_S = 120
