# adBlockr - network-wide DNS ad blocker for the NM-CYD-C5 (ESP32-C5), MicroPython edition.
# Point your router's DHCP "DNS server" at this device: listed ad/tracker domains get
# 0.0.0.0 / ::, everything else is forwarded to the upstream resolver.
import asyncio
import gc
import time
import machine
import network
import blocklist
import dns
import gfx
import settings
import stats
import ui
import web
from config import *

_np = None
_led_off = 0


def led(r, g, b):
    if _np:
        _np[0] = (r, g, b)
        _np.write()


def led_flash():
    global _led_off
    led(60, 0, 0)
    _led_off = time.ticks_add(time.ticks_ms(), 60)


def ntp():
    try:
        import ntptime
        ntptime.host = "pool.ntp.org"
        ntptime.settime()               # sets the RTC to UTC
        return True
    except Exception as e:
        print("ntp:", e)
        return False


def connect(wlan):
    s = settings.s
    try:
        network.hostname(HOSTNAME)      # also the mDNS name: http://adblockr.local
    except Exception:
        pass
    wlan.active(True)
    try:
        wlan.config(pm=wlan.PM_NONE)    # no power save: lowest DNS latency
    except Exception:
        pass
    if s["ip"] and s["gw"]:
        wlan.ifconfig((s["ip"], s["mask"] or "255.255.255.0", s["gw"], s["up1"]))
    wlan.connect(s["ssid"], s["pw"])
    ui.splash("Connecting to Wi-Fi", s["ssid"])
    t0 = time.ticks_ms()
    while not wlan.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < WIFI_CONNECT_TIMEOUT_MS:
        time.sleep_ms(250)
    if not wlan.isconnected():
        return False
    try:
        network.ipconfig(dns=s["up1"])  # the blocker resolves via the upstream, never via itself
    except Exception:
        pass
    return True


async def setup_portal(wlan):
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    try:
        ap.config(essid=SETUP_AP_SSID, security=0)
    except Exception:
        ap.config(essid=SETUP_AP_SSID, authmode=0)
    wlan.active(True)                   # STA on too, for the network scan
    ap_ip = ap.ifconfig()[0]
    ui.setup_mode(SETUP_AP_SSID, ap_ip)
    led(0, 0, 40)
    await web.start(portal=True)
    await dns.captive(ap_ip)


async def run(wlan):
    global _led_off
    cfg = wlan.ifconfig()
    dns.set_network(cfg[0], cfg[1], cfg[2])
    clock_ok = ntp()
    dns.on_block = led_flash
    dns.start()
    await web.start()
    ui.start_dashboard()
    asyncio.create_task(ui.run())
    led(0, 8, 0)
    print("adBlockr ready: DNS on %s:53, web on http://%s/" % (cfg[0], cfg[0]))
    if not blocklist.status["domains"]:
        asyncio.create_task(blocklist.update())         # first boot: download now
    last_list = last_ntp = time.ticks_ms()
    lost_at = 0
    while True:
        await asyncio.sleep(1)
        now = time.ticks_ms()
        try:
            stats.tick()
            if _led_off and time.ticks_diff(now, _led_off) >= 0:
                led(0, 0 if dns.paused() else 6, 6 if dns.paused() else 0)   # green active, blue paused
                _led_off = 0
            ls = blocklist.status
            refresh = LIST_REFRESH_HOURS * 3600000 if ls["domains"] and not ls["err"] else 3600000
            if time.ticks_diff(now, last_list) > refresh:
                last_list = now
                asyncio.create_task(blocklist.update())
            if time.ticks_diff(now, last_ntp) > (86400000 if clock_ok else 3600000):
                last_ntp = now
                clock_ok = ntp() or clock_ok
            if not wlan.isconnected():                  # Wi-Fi watchdog
                if not lost_at:
                    lost_at = now
                elif time.ticks_diff(now, lost_at) > 30000:
                    lost_at = now
                    wlan.connect(settings.s["ssid"], settings.s["pw"])
            elif lost_at:
                lost_at = 0
                cfg = wlan.ifconfig()
                dns.set_network(cfg[0], cfg[1], cfg[2])
        except Exception as e:
            print("main:", repr(e))


def boot():
    global _np
    settings.load()
    d = gfx.Display()
    ui.begin(d)
    try:
        from neopixel import NeoPixel
        _np = NeoPixel(machine.Pin(PIN_LED), 1)
    except Exception:
        _np = None
    led(20, 10, 0)
    ui.splash("Starting...", "hold the screen now to recalibrate touch")
    time.sleep_ms(1500)
    ui.calibrate(ui.touched_now())
    ui.splash("Loading blocklist cache...")
    blocklist.init()
    gc.collect()
    wlan = network.WLAN(network.STA_IF)
    ui.wlan = web.wlan = wlan
    web.on_brightness = ui.set_brightness
    if not settings.s["ssid"] or not connect(wlan):
        asyncio.run(setup_portal(wlan))
    else:
        asyncio.run(run(wlan))


try:
    boot()
except KeyboardInterrupt:
    print("stopped (Ctrl-C): the REPL is free for mpremote")
except Exception as e:
    import sys
    sys.print_exception(e)
    try:
        ui.splash("Error - restarting in 10 s", repr(e)[:44])
    except Exception:
        pass
    time.sleep(10)
    machine.reset()
