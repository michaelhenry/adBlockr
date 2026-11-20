# Touchscreen UI: dashboard, settings, Wi-Fi picker + keyboard, about, confirm dialogs.
# iOS dark-mode look: black page, #1C1C1E pills with blue icons, Inter type.
import asyncio
import gc
import math
import time
import machine
import blocklist
import dns
import settings
import stats
import tz
from gfx import rgb, Font, W, H
from config import *

BG = rgb(0, 0, 0)
FILL = rgb(0x1C, 0x1C, 0x1E)       # buttons, keys, fields
EDGE = rgb(0x38, 0x38, 0x3A)       # separators
BAR = rgb(0x48, 0x48, 0x4A)        # graph queries
TEXT = rgb(255, 255, 255)
DIM = rgb(0x8E, 0x8E, 0x93)
ACCENT = rgb(0x0A, 0x84, 0xFF)
RED = rgb(0xFF, 0x45, 0x3A)
GREEN = rgb(0x30, 0xD1, 0x58)
ORANGE = rgb(0xFF, 0x9F, 0x0A)

d = None                           # gfx.Display
wlan = None                        # set by main.py
S = M = B = None                   # fonts: small, title, big number
screen = "splash"

B_PAUSE, B_UPDATE, B_SET = (8, 196, 98, 40), (111, 196, 98, 40), (214, 196, 98, 40)
B_BACK, B_MID, B_RIGHT = B_PAUSE, B_UPDATE, B_SET
B_NO, B_YES = (40, 150, 116, 40), (164, 150, 116, 40)
ICONS = ("pause", "play", "refresh", "gear", "back", "power", "trash")


def begin(display):
    global d, S, M, B
    d = display
    S, M, B = Font("/fonts/s.fnt"), Font("/fonts/m.fnt"), Font("/fonts/b.fnt")
    d.fill(BG)
    d.show()
    set_brightness(settings.s["bright"])


def set_brightness(v):
    d.brightness(v)


def hit(b, x, y):
    return b[0] <= x < b[0] + b[2] and b[1] <= y < b[1] + b[3]


def fmt_num(v):
    s, out = str(v), ""
    while len(s) > 3:
        out = "," + s[-3:] + out
        s = s[:-3]
    return s + out


def fmt_ago(t):
    if not t:
        return "never"
    dt = tz.now() - t
    if dt < 90:
        return "just now"
    if dt < 5400:
        return "%d min ago" % (dt // 60)
    if dt < 172800:
        return "%d h ago" % (dt // 3600)
    return "%d days ago" % (dt // 86400)


def ip():
    try:
        return wlan.ifconfig()[0]
    except Exception:
        return "-"


def ssid():
    try:
        return wlan.config("ssid") if wlan.isconnected() else ""
    except Exception:
        return settings.s["ssid"]


def fit(s, font, w):
    while len(s) > 1 and font.width(s) > w:
        s = s[:-2] + "~"
    return s


def title(t):
    d.fill(BG)
    d.text(t, 12, 4, M, TEXT, BG)


# --------------------------------------------------------------------------- icons
def glyph(ic, cx, cy, c, bg):
    if ic == "pause":
        d.rrect(cx - 6, cy - 8, 4, 16, 1, c)
        d.rrect(cx + 2, cy - 8, 4, 16, 1, c)
    elif ic == "play":
        d.tri(cx - 5, cy - 8, cx - 5, cy + 8, cx + 8, cy, c)
    elif ic == "refresh":       # circle open at the top-right, arrowhead at 12 o'clock
        d.arc(cx, cy, 7, 3, 240, 180, c)
        d.tri(cx - 1, cy - 11, cx - 1, cy - 3, cx + 5, cy - 7, c)
    elif ic == "gear":
        for i in range(8):
            a = i * math.pi / 4
            d.circle(cx + round(7 * math.cos(a)), cy + round(7 * math.sin(a)), 2, c)
        d.circle(cx, cy, 6, c)
        d.circle(cx, cy, 2, bg)
    elif ic == "back":          # chevron-left
        d.wline(cx + 3, cy - 7, cx - 4, cy, 3, c)
        d.wline(cx - 4, cy, cx + 3, cy + 7, 3, c)
    elif ic == "power":
        d.arc(cx, cy + 1, 7, 3, 215, 145, c)
        d.wline(cx, cy - 9, cx, cy, 3, c)
    elif ic == "trash":
        d.rrect(cx - 7, cy - 7, 14, 3, 1, c)
        d.rect(cx - 2, cy - 9, 4, 2, c)
        d.rrect(cx - 5, cy - 3, 10, 12, 2, c)
        d.vline(cx - 2, cy - 1, 8, bg)
        d.vline(cx + 1, cy - 1, 8, bg)


def button(b, what, fill=FILL, color=ACCENT):
    x, y, w, h = b
    d.rrect(x, y, w, h, h // 2, fill)
    if what in ICONS:
        glyph(what, x + w // 2, y + h // 2, color, fill)
    else:
        d.text(what, x + w // 2, y + (h - S.h) // 2, S, color, fill, "c")


def chevron(x, cy):
    d.line(x, cy - 4, x + 4, cy, DIM)
    d.line(x + 4, cy, x, cy + 4, DIM)


# --------------------------------------------------------------------------- boot screens
def splash(l1, l2=""):
    global screen
    screen = "splash"
    d.fill(BG)
    d.circle(160, 62, 18, ACCENT)
    d.rrect(151, 59, 18, 6, 3, TEXT)                    # "no entry" mark
    d.text("adBlockr", 160, 88, M, TEXT, BG, "c")
    d.text(l1, 160, 128, S, TEXT, BG, "c")
    d.text(l2, 160, 148, S, DIM, BG, "c")
    d.text("v" + VERSION, 160, 214, S, DIM, BG, "c")
    d.show()


def setup_mode(ap_ssid, ap_ip):
    global screen
    screen = "setup"
    title("Wi-Fi Setup")
    d.text("1. On your phone, join Wi-Fi:", 12, 46, S, TEXT, BG)
    d.text(ap_ssid, 28, 66, M, ACCENT, BG)
    d.text("2. The setup page should open.", 12, 102, S, TEXT, BG)
    d.text("    If not, browse to:", 12, 120, S, TEXT, BG)
    d.text("http://" + ap_ip, 28, 140, M, ACCENT, BG)
    d.text("3. Choose your network and an admin", 12, 182, S, DIM, BG)
    d.text("    password. The device then restarts.", 12, 200, S, DIM, BG)
    d.show()


# --------------------------------------------------------------------------- touch
def touched_now():
    return d.touch_raw()[2] > 600


def touch():
    """Calibrated (x, y) or None."""
    x, y, z = d.touch_raw()
    c = settings.s["tcal"]
    if z < 600 or not c:
        return None
    a0, a1, b0, b1, swap = c
    a, b = (y, x) if swap else (x, y)
    sx = 20 + (a - a0) * 280 // (a1 - a0)
    sy = 20 + (b - b0) * 200 // (b1 - b0)
    return max(0, min(W - 1, sx)), max(0, min(H - 1, sy))


def _capture(px, py):
    d.fill(BG)
    d.text("Touch calibration", 160, 90, M, TEXT, BG, "c")
    d.text("Tap the target precisely", 160, 126, S, DIM, BG, "c")
    d.circle(px, py, 9, ACCENT)
    d.circle(px, py, 6, BG)
    d.hline(px - 14, py, 29, ACCENT)
    d.vline(px, py - 14, 29, ACCENT)
    d.show()
    while d.touch_raw()[2] > 600:                       # wait for any earlier press to end
        time.sleep_ms(20)
    xs, ys = [], []
    while len(xs) < 8:
        x, y, z = d.touch_raw()
        if z > 600:
            xs.append(x)
            ys.append(y)
        time.sleep_ms(15)
    while d.touch_raw()[2] > 600:
        time.sleep_ms(20)
    time.sleep_ms(150)
    xs.sort()
    ys.sort()
    return xs[4], ys[4]


def calibrate(force=False):
    """Three-point calibration. Blocks (DNS waits for those few seconds)."""
    if settings.s["tcal"] and not force:
        return
    while True:
        p0, p1, p2 = _capture(20, 20), _capture(300, 20), _capture(20, 220)
        swap = abs(p1[1] - p0[1]) > abs(p1[0] - p0[0])  # panel axes rotated vs the screen
        c = [p0[1], p1[1], p0[0], p2[0], 1] if swap else [p0[0], p1[0], p0[1], p2[1], 0]
        if abs(c[1] - c[0]) > 200 and abs(c[3] - c[2]) > 200:
            break
    settings.s["tcal"] = c
    settings.save()
    d.fill(BG)
    d.show()


# --------------------------------------------------------------------------- dashboard
def status_pill():
    if blocklist.status["updating"]:
        return "Updating", ACCENT
    if dns.paused():
        r = dns.pause_remaining()
        return "Paused %d:%02d" % (r // 60, r % 60), ORANGE
    if not wlan or not wlan.isconnected():
        return "No Wi-Fi", RED
    if not blocklist.status["domains"]:
        return "No list", RED
    return "Protected", GREEN


def header():
    d.text("adBlockr", 12, 4, M, TEXT, BG)
    st, sc = status_pill()
    d.rect(150, 4, 170, 28, BG)
    w = d.text(st, 308, 9, S, TEXT, BG, "r")
    d.circle(308 - w - 9, 18, 4, sc)


def stat_line(y, label, val, color):
    d.text(val, 308, y, S, color, BG, "r", clear=118)  # value first: its band clears stale text
    d.text(label, 186, y, S, DIM, BG)


def dash_values():
    header()
    d.text(fmt_num(stats.blocked), 12, 34, B, TEXT, BG, clear=170)
    d.text("blocked today", 12, 86, S, DIM, BG)
    ls = blocklist.status
    stat_line(38, "Queries", fmt_num(stats.queries), TEXT)
    stat_line(56, "Blocked", "%d%%" % stats.pct(), RED)
    stat_line(74, "IP", ip(), ACCENT)
    stat_line(92, "List", "%d/%d" % (ls["src"], ls["srcs"]) if ls["updating"] else fmt_num(ls["domains"]), TEXT)
    d.hline(12, 113, 296, EDGE)
    d.text("Last hour", 12, 116, S, DIM, BG)
    lb = stats.last_blocked or "Nothing blocked yet"
    d.rect(8, 176, 304, S.h, BG)
    d.circle(15, 185, 3, RED if stats.last_blocked else DIM)
    d.text(fit(lb, S, 284), 24, 176, S, TEXT, BG)


def graph():
    y0, h = 136, 36
    d.rect(12, y0, 296, h + 2, BG)
    hist = [stats.history(i) for i in range(stats.HIST_MIN)]
    mx = max(1, max(q for q, _ in hist))
    d.hline(12, y0 + h + 1, 296, EDGE)
    for i, (q, b) in enumerate(hist):
        x = 14 + i * 294 // stats.HIST_MIN
        hq = max(1, q * h // mx) if q else 0
        hb = max(1, b * h // mx) if b else 0
        if hq:
            d.rect(x, y0 + h + 1 - hq, 3, hq, BAR)
        if hb:
            d.rect(x, y0 + h + 1 - hb, 3, hb, RED)


def dash_buttons():
    if dns.paused():
        button(B_PAUSE, "play", ORANGE, BG)
    else:
        button(B_PAUSE, "pause")
    button(B_UPDATE, "refresh", FILL, DIM if blocklist.status["updating"] else ACCENT)
    button(B_SET, "gear")


def start_dashboard():
    global screen
    screen = "dash"
    d.fill(BG)
    dash_values()
    graph()
    dash_buttons()
    d.show()


# --------------------------------------------------------------------------- about
def info_row(i, label, val, last):
    y = 36 + i * 17
    d.text(label, 18, y - 1, S, DIM, BG)
    d.text(fit(val, S, 284 - S.width(label) - 10), 302, y - 1, S, TEXT, BG, "r")
    if not last:
        d.hline(18, y + 16, 294, EDGE)


def draw_info():
    global screen
    screen = "info"
    title("About")
    ls = blocklist.status
    try:
        ch, rssi, cfg = wlan.config("channel"), wlan.status("rssi"), wlan.ifconfig()
    except Exception:
        ch, rssi, cfg = 0, 0, ("-", "-", "-", "-")
    gc.collect()
    rows = [
        ("Wi-Fi", ssid()),
        ("Signal", "%s ch%d, %d dBm" % ("5 GHz" if ch > 14 else "2.4 GHz", ch, rssi)),
        ("IP / Gateway", "%s / %s" % (cfg[0], cfg[2])),
        ("Web", HOSTNAME + ".local"),
        ("Upstream", "%s, %s (%d ms)" % (settings.s["up1"], settings.s["up2"], stats.avg_latency)),
        ("Blocklist", "%s domains, %s" % (fmt_num(ls["domains"]), fmt_ago(ls["last"]))),
        ("Last error", ls["err"]) if ls["err"] else
        ("Since boot", "%s q, %s blocked" % (fmt_num(stats.total_queries), fmt_num(stats.total_blocked))),
        ("Memory", "%d KB free" % (gc.mem_free() // 1024)),
        ("Firmware", "v%s, up %d h" % (VERSION, time.ticks_ms() // 3600000)),
    ]
    for i, (k, v) in enumerate(rows):
        info_row(i, k, v, i == len(rows) - 1)
    button(B_BACK, "back")
    d.show()


# --------------------------------------------------------------------------- settings
SET_Y, SET_RH, SET_ROWS = 38, 26, 6
SL_X0, SL_X1 = 130, 296
DIM_STEPS = (0, 30, 60, 120, 300, 600)


def dim_label(s):
    if not s:
        return "Never"
    return "%d s" % s if s < 60 else "%d min" % (s // 60)


def settings_row(i, label, val, more, last):
    y = SET_Y + i * SET_RH
    ty = y + (SET_RH - S.h) // 2
    d.rect(8, y, 304, SET_RH - 1, BG)
    d.text(fit(label, S, 200), 18, ty, S, TEXT, BG)
    if val:
        d.text(fit(val, S, 150), 290 if more else 302, ty, S, DIM if more else ACCENT, BG, "r")
    if more:
        chevron(298, y + SET_RH // 2)
    if not last:
        d.hline(18, y + SET_RH - 1, 294, EDGE)


def slider():
    cy = SET_Y + SET_RH // 2
    d.rect(SL_X0 - 10, cy - 10, SL_X1 - SL_X0 + 20, 21, BG)
    kx = SL_X0 + (settings.s["bright"] - 10) * (SL_X1 - SL_X0) // 245
    d.rrect(SL_X0, cy - 2, SL_X1 - SL_X0, 4, 2, EDGE)
    d.rrect(SL_X0, cy - 2, kx - SL_X0 + 1, 4, 2, ACCENT)
    d.circle(kx, cy, 9, EDGE)                           # knob with a hairline ring, like iOS
    d.circle(kx, cy, 8, TEXT)


def draw_settings():
    global screen
    screen = "settings"
    title("Settings")
    settings_row(0, "Brightness", "", False, False)
    slider()
    settings_row(1, "Dim screen", dim_label(settings.s["dim"]), False, False)
    settings_row(2, "Wi-Fi", ssid(), True, False)
    settings_row(3, "Calibrate touch", "", True, False)
    settings_row(4, "Admin login", settings.s["auser"], True, False)
    settings_row(5, "About", "", True, True)
    button(B_BACK, "back")
    button(B_MID, "power")
    button(B_RIGHT, "trash", FILL, RED)
    d.show()


def row_at(y, rows=SET_ROWS):
    if y < SET_Y or y >= SET_Y + rows * SET_RH:
        return -1
    return (y - SET_Y) // SET_RH


def brightness_from_x(x):
    v = 10 + (max(SL_X0, min(SL_X1, x)) - SL_X0) * 245 // (SL_X1 - SL_X0)
    if v != settings.s["bright"]:
        settings.s["bright"] = v
        set_brightness(v)
        slider()
        d.show()


# --------------------------------------------------------------------------- confirm
asking = None


def draw_confirm(what):
    global screen, asking
    screen, asking = "confirm", what
    d.fill(EDGE)                                        # dimmed backdrop
    d.rrect(30, 46, 260, 154, 14, BG)
    reset = what == "reset"
    d.text("Reset adBlockr?" if reset else "Restart adBlockr?", 160, 60, M, TEXT, BG, "c")
    if reset:
        d.text("Erases Wi-Fi, password, lists and", 160, 96, S, DIM, BG, "c")
        d.text("settings, then opens setup.", 160, 114, S, DIM, BG, "c")
    else:
        d.text("Ad blocking stops for ~20 s.", 160, 104, S, DIM, BG, "c")
    button(B_NO, "Cancel")
    button(B_YES, "Reset" if reset else "Restart", RED if reset else ACCENT, TEXT)
    d.show()


# --------------------------------------------------------------------------- Wi-Fi
nets = []                       # [(ssid, is_open)]
join_ssid = ""


def scan_wifi():
    global nets
    title("Wi-Fi")
    d.text("Scanning...", 18, 46, S, DIM, BG)
    d.show()
    best = {}
    try:
        for n in wlan.scan():                           # blocks ~3 s; DNS answers wait meanwhile
            name = n[0].decode() if isinstance(n[0], bytes) else n[0]
            if name and (name not in best or n[3] > best[name][0]):
                best[name] = (n[3], n[4] == 0)          # strongest per SSID (mesh nodes repeat it)
    except Exception as e:
        print("scan:", e)
    nets = [(k, v[1]) for k, v in sorted(best.items(), key=lambda kv: -kv[1][0])][:6]


def draw_wifi():
    global screen
    screen = "wifi"
    title("Wi-Fi")
    if not nets:
        d.text("No networks found.", 18, 46, S, DIM, BG)
    cur = ssid()
    for i, (name, op) in enumerate(nets):
        here = name == cur
        settings_row(i, name, "Connected" if here else ("Open" if op else ""), not here, i == len(nets) - 1)
    button(B_BACK, "back")
    button(B_RIGHT, "refresh")
    d.show()


def join_wifi(name, pw):
    """Try the network; keep it only once it connects, otherwise restart onto the saved one."""
    splash("Joining Wi-Fi", name)
    wlan.disconnect()
    if name != settings.s["ssid"]:
        try:
            wlan.ipconfig(dhcp4=True)                   # a new network: no static IP
        except Exception:
            pass
    wlan.connect(name, pw)
    t0 = time.ticks_ms()
    while not wlan.isconnected() and time.ticks_diff(time.ticks_ms(), t0) < 20000:
        time.sleep_ms(250)
    if wlan.isconnected():
        if name != settings.s["ssid"]:
            settings.s["ip"] = settings.s["gw"] = settings.s["mask"] = ""
        settings.s["ssid"], settings.s["pw"] = name, pw
        settings.save()
        splash("Connected", "Restarting...")
    else:
        splash("Couldn't join", "Check the password. Going back...")
    time.sleep_ms(1500)
    machine.reset()


# --------------------------------------------------------------------------- keyboard
KB = (("qwertyuiop", "asdfghjkl", "zxcvbnm"),
      ("QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"),
      ("1234567890", "-/:;()$&@\"", ".,?!'"),
      ("[]{}#%^*+=", "_\\|~<>`", ".,?!'"))
KB_Y, KB_RH, KB_KH = 98, 35, 31
SHIFT, DEL, MODE, DONE = "\x01", "\x02", "\x03", "\x04"
kb_layer = 0
kb_for = "wifi"                 # wifi | user | pass
kb_buf = ""
kb_err = ""
pending_user = ""


def kb_keys():
    keys = []
    for r in range(3):
        row = KB[kb_layer][r]
        side = 46 if r == 2 else 0
        span = 316 - 2 * side
        pitch = span // (10 if r < 2 else 7)
        x0 = 2 + side + (span - pitch * len(row)) // 2
        y = KB_Y + r * KB_RH
        for i, ch in enumerate(row):
            keys.append((x0 + i * pitch, y, pitch - 3, ch))
        if r == 2:
            keys.append((2, y, 42, SHIFT))
            keys.append((276, y, 42, DEL))
    y = KB_Y + 3 * KB_RH
    keys += [(2, y, 60, MODE), (66, y, 156, " "), (226, y, 92, DONE)]
    return keys


def kb_label(c):
    if c == SHIFT:
        return ("shift", "SHIFT", "#+=", "123")[kb_layer]
    if c == DEL:
        return "del"
    if c == MODE:
        return "ABC" if kb_layer >= 2 else "123"
    if c == DONE:
        return {"wifi": "Join", "user": "Next"}.get(kb_for, "Save")
    return "space" if c == " " else c


def draw_key(k, down=False):
    x, y, w, c = k
    special = c < " "
    fill = EDGE if down else ACCENT if c == DONE else EDGE if special else FILL
    d.rrect(x, y, w, KB_KH, 6, fill)
    d.text(kb_label(c), x + w // 2, y + (KB_KH - S.h) // 2, S, TEXT, fill, "c")


def draw_field():
    d.rrect(8, 54, 304, 34, 10, FILL)
    v = kb_buf or ("Username" if kb_for == "user" else "Password")
    while S.width(v) > 280:
        v = v[1:]                                       # keep the end visible while typing
    w = d.text(v, 18, 62, S, TEXT if kb_buf else DIM, FILL)
    if kb_buf:
        d.vline(19 + w, 62, 18, ACCENT)                 # caret


def draw_keyboard():
    d.rect(0, KB_Y, W, H - KB_Y, BG)
    for k in kb_keys():
        draw_key(k)


def draw_keys():
    global screen
    screen = "keys"
    d.fill(BG)
    d.text("Cancel", 12, 7, S, ACCENT, BG)
    t = join_ssid if kb_for == "wifi" else "Admin login"
    d.text(fit(t, S, 180), 180, 7, S, TEXT, BG, "c")
    hint = kb_err or {"wifi": "Enter the Wi-Fi password", "user": "Web dashboard username"}.get(
        kb_for, "New password, 8+ characters")
    d.text(hint, 12, 32, S, RED if kb_err else DIM, BG)
    draw_field()
    draw_keyboard()
    d.show()


def open_keys(what, initial=""):
    global kb_for, kb_buf, kb_err, kb_layer
    kb_for, kb_buf, kb_err, kb_layer = what, initial, "", 0
    draw_keys()


def key_done():
    global kb_err, pending_user
    if kb_for == "wifi":
        join_wifi(join_ssid, kb_buf)
        return
    if kb_for == "user":
        u = kb_buf.strip()
        if not u or ":" in u:
            kb_err = "Username can't be empty or contain ':'"
            draw_keys()
            return
        pending_user = u
        open_keys("pass")
        return
    if len(kb_buf) < 8:
        kb_err = "Password needs at least 8 characters"
        draw_keys()
        return
    settings.s["auser"], settings.s["apass"] = pending_user, kb_buf
    settings.save()
    draw_settings()


def key_tap(x, y):
    global kb_buf, kb_layer
    if x < 90 and y < 32:                               # Cancel
        if kb_for == "wifi":
            draw_wifi()
        else:
            draw_settings()
        return
    for k in kb_keys():
        kx, ky, kw, c = k
        if not (kx <= x < kx + kw + 3 and ky <= y < ky + KB_RH):
            continue
        draw_key(k, True)
        d.show()
        time.sleep_ms(50)
        if c == DONE:
            key_done()
            return
        if c == SHIFT:
            kb_layer = (1, 0, 3, 2)[kb_layer]
            draw_keyboard()
            d.show()
            return
        if c == MODE:
            kb_layer = 0 if kb_layer >= 2 else 2
            draw_keyboard()
            d.show()
            return
        if c == DEL:
            kb_buf = kb_buf[:-1]
        elif len(kb_buf) < (32 if kb_for == "user" else 63):   # 63 = WPA2 max passphrase
            kb_buf += c
        draw_key(k)
        if kb_layer == 1 and c > " ":                   # shift is one-shot
            kb_layer = 0
            draw_keyboard()
        draw_field()
        d.show()
        return


# --------------------------------------------------------------------------- touch routing
def on_tap(x, y):
    global join_ssid
    if screen == "dash":
        if hit(B_PAUSE, x, y):
            dns.pause(0 if dns.paused() else 300)
            dash_buttons()
            header()
            d.show()
        elif hit(B_UPDATE, x, y):
            asyncio.create_task(blocklist.update())
            dash_buttons()
            d.show()
        elif hit(B_SET, x, y):
            draw_settings()
    elif screen == "info":
        if hit(B_BACK, x, y):
            draw_settings()
    elif screen == "settings":
        if hit(B_BACK, x, y):
            settings.save()
            start_dashboard()
        elif hit(B_MID, x, y):
            draw_confirm("restart")
        elif hit(B_RIGHT, x, y):
            draw_confirm("reset")
        else:
            r = row_at(y)
            if r == 0:
                brightness_from_x(x)
            elif r == 1:
                cur = settings.s["dim"]
                i = DIM_STEPS.index(cur) if cur in DIM_STEPS else -1
                settings.s["dim"] = DIM_STEPS[(i + 1) % len(DIM_STEPS)]
                settings_row(1, "Dim screen", dim_label(settings.s["dim"]), False, False)
                d.show()
            elif r == 2:
                scan_wifi()
                draw_wifi()
            elif r == 3:
                calibrate(True)
                draw_settings()
            elif r == 4:
                open_keys("user", settings.s["auser"])
            elif r == 5:
                draw_info()
    elif screen == "wifi":
        if hit(B_BACK, x, y):
            draw_settings()
        elif hit(B_RIGHT, x, y):
            scan_wifi()
            draw_wifi()
        else:
            r = row_at(y, len(nets))
            if 0 <= r < len(nets) and nets[r][0] != ssid():
                join_ssid = nets[r][0]
                if nets[r][1]:
                    join_wifi(join_ssid, "")
                else:
                    open_keys("wifi")
    elif screen == "keys":
        key_tap(x, y)
    elif screen == "confirm":
        if hit(B_NO, x, y):
            draw_settings()
        elif hit(B_YES, x, y):
            settings.save()
            if asking == "reset":
                splash("Resetting...", "Erasing settings and lists")
                settings.factory_reset()
            else:
                splash("Restarting...")
            time.sleep_ms(800)
            machine.reset()


async def run():
    """Touch polling, redraws and screen dimming."""
    was = dimmed = False
    last_touch = time.ticks_ms()
    last_draw = last_graph = 0
    last_state = last_vals = None
    while True:
        await asyncio.sleep_ms(25)
        if screen in ("splash", "setup"):
            continue
        now = time.ticks_ms()
        p = touch()
        if p and not was:
            last_touch = now
            if dimmed:
                dimmed = False
                set_brightness(settings.s["bright"])
            else:
                try:
                    on_tap(*p)
                except Exception as e:
                    print("ui:", repr(e))
        elif p and screen == "settings" and row_at(p[1]) == 0:
            last_touch = now
            brightness_from_x(p[0])                     # drag the slider
        was = p is not None
        dim_s = settings.s["dim"]
        if not dimmed and dim_s and time.ticks_diff(now, last_touch) > dim_s * 1000:
            dimmed = True
            set_brightness(12)
        if screen == "dash":
            if time.ticks_diff(now, last_draw) >= 1000:
                last_draw = now
                ls = blocklist.status
                vals = (stats.blocked, stats.queries, ip(), ls["domains"], ls["src"], ls["updating"],
                        status_pill()[0], stats.last_blocked)
                if vals != last_vals:                   # skip the redraw (and its SPI time) when idle
                    last_vals = vals
                    dash_values()
                state = (dns.paused(), ls["updating"])
                if state != last_state:
                    dash_buttons()
                    last_state = state
                if time.ticks_diff(now, last_graph) >= 5000:
                    last_graph = now
                    graph()
                d.show()
        else:
            last_state = last_vals = None
