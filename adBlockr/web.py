# Web dashboard + setup portal: a small asyncio HTTP/1.1 server (one request per connection).
import asyncio
import binascii
import gc
import json
import os
import time
import machine
import blocklist
import dns
import settings
import stats
from config import *

wlan = None              # set by main.py
on_brightness = None     # set by main.py (ui.set_brightness)
_portal = False
WWW = "/www/"
MAX_BODY = 32768


def _unquote(s):
    s = s.replace("+", " ")
    if "%" not in s:
        return s
    raw, b, i = s.encode(), bytearray(), 0
    while i < len(raw):
        if raw[i] == 37 and i + 3 <= len(raw):   # '%XX'
            try:
                b.append(int(raw[i + 1:i + 3].decode(), 16))
                i += 3
                continue
            except ValueError:
                pass
        b.append(raw[i])
        i += 1
    return b.decode()


def _form(s):
    out = {}
    for part in s.split("&"):
        if part:
            k, _, v = part.partition("=")
            out[_unquote(k)] = _unquote(v)
    return out


def _ipv4(s):
    p = s.split(".")
    return len(p) == 4 and all(x.isdigit() and 0 <= int(x) <= 255 for x in p)


async def _send(w, code, ctype, body, extra=""):
    if isinstance(body, str):
        body = body.encode()
    reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found"}.get(code, "OK")
    w.write(("HTTP/1.1 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\n%s\r\n"
             % (code, reason, ctype, len(body), extra)).encode())
    w.write(body)
    await w.drain()


async def _file(w, name, ctype):
    path = WWW + name
    try:
        size = os.stat(path)[6]
    except OSError:
        await _send(w, 404, "text/plain", "not found")
        return
    w.write(("HTTP/1.1 200 OK\r\nContent-Type: %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n"
             % (ctype, size)).encode())
    buf = bytearray(1024)
    with open(path, "rb") as f:
        while True:
            n = f.readinto(buf)
            if not n:
                break
            w.write(bytes(buf[:n]))
            await w.drain()


def _authed(headers):
    if _portal or not settings.s["apass"]:
        return True
    h = headers.get("authorization", "")
    if not h.startswith("Basic "):
        return False
    try:
        user, _, pw = binascii.a2b_base64(h[6:]).decode().partition(":")
    except Exception:
        return False
    return user == settings.s["auser"] and pw == settings.s["apass"]


def _reboot_later(ms=1500):
    async def go():
        await asyncio.sleep_ms(ms)
        machine.reset()
    asyncio.create_task(go())


# --------------------------------------------------------------------------- JSON
def _stats_json():
    ls = blocklist.status
    try:
        rssi, ch, ssid = wlan.status("rssi"), wlan.config("channel"), wlan.config("ssid")
    except Exception:
        rssi, ch, ssid = 0, 0, settings.s["ssid"]
    top = sorted(stats.top.items(), key=lambda kv: -kv[1])[:10]
    log = [[t if t > 1700000000 else 0, n, c, stats.qtype_name(q), r] for (t, n, c, q, r) in reversed(stats.log)]
    return json.dumps({
        "queries": stats.queries, "blocked": stats.blocked, "pct": stats.pct(),
        "fwd": stats.forwarded, "failed": stats.failed, "lat": stats.avg_latency,
        "paused": dns.paused(), "pause_s": dns.pause_remaining(),
        "up": time.ticks_ms() // 1000, "rssi": rssi, "ch": ch, "ssid": ssid, "ver": VERSION,
        "list": {"domains": ls["domains"], "progress": ls["progress"], "src": ls["src"], "srcs": ls["srcs"],
                 "cap": ls["cap"], "last": ls["last"], "updating": ls["updating"], "err": ls["err"]},
        "hist": [list(stats.history(i)) for i in range(stats.HIST_MIN)],
        "top": [[k, v] for k, v in top],
        "log": log,
    })


def _config_json():
    s = settings.s
    return json.dumps({
        "up1": s["up1"], "up2": s["up2"], "local": s["local"], "subdom": s["subdom"],
        "auser": s["auser"], "bright": s["bright"], "dim": s["dim"], "tz": s["tz"],
        "lists": settings.read_text(LISTS_FILE, DEFAULT_LISTS),
        "allow": settings.read_text(ALLOW_FILE), "block": settings.read_text(BLOCK_FILE),
    })


def _config_post(a):
    """Apply a settings form. Returns an error message, or None when saved."""
    s = settings.s
    for k in ("up1", "up2"):
        if k in a and not _ipv4(a[k]):
            return "Upstream %s must be an IPv4 address" % k[-1]
    if "auser" in a:
        u = a["auser"].strip()
        if not u or len(u) > 32 or ":" in u:
            return "Username must be 1-32 characters, no colon"
    if a.get("apass") and len(a["apass"]) < 8:
        return "Admin password needs at least 8 characters"
    for k in ("up1", "up2"):
        if k in a:
            s[k] = a[k]
    if "auser" in a:
        s["auser"] = a["auser"].strip()
    if a.get("apass"):
        s["apass"] = a["apass"]
    if "local" in a:
        s["local"] = a["local"] == "1"
    if "subdom" in a:
        s["subdom"] = a["subdom"] == "1"
    if "bright" in a and a["bright"].isdigit():
        s["bright"] = max(10, min(255, int(a["bright"])))
    if "dim" in a and a["dim"].isdigit():
        s["dim"] = max(0, min(3600, int(a["dim"])))
    if a.get("tz"):
        s["tz"] = a["tz"]
    settings.save()
    dns.reload_upstreams()
    if on_brightness:
        on_brightness(s["bright"])
    return None


# --------------------------------------------------------------------------- routing
async def _admin(w, method, path, a, headers):
    if path == "/style.css":
        return await _file(w, "style.css", "text/css")
    if not _authed(headers):
        return await _send(w, 401, "text/plain", "login required", 'WWW-Authenticate: Basic realm="adBlockr"\r\n')
    if path == "/":
        return await _file(w, "index.html", "text/html")
    if path == "/settings":
        return await _file(w, "settings.html", "text/html")
    if path == "/api/stats":
        gc.collect()
        return await _send(w, 200, "application/json", _stats_json())
    if path == "/api/config":
        if method == "POST":
            err = _config_post(a)
            if err:
                return await _send(w, 400, "text/plain", err)
            changed = False
            if "lists" in a:
                changed = a["lists"] != settings.read_text(LISTS_FILE, DEFAULT_LISTS)
                settings.write_text(LISTS_FILE, a["lists"])
            if "allow" in a:
                settings.write_text(ALLOW_FILE, a["allow"])
            if "block" in a:
                settings.write_text(BLOCK_FILE, a["block"])
            blocklist.reload_local()
            if changed:
                asyncio.create_task(blocklist.update())
            return await _send(w, 200, "text/plain", "Saved - downloading new lists" if changed else "Saved")
        return await _send(w, 200, "application/json", _config_json())
    if method != "POST":
        return await _send(w, 404, "text/plain", "not found")
    if path == "/api/allow":
        d = a.get("d", "").strip().lower()
        if not d or len(d) > 253 or "\n" in d:
            return await _send(w, 400, "text/plain", "bad domain")
        cur = settings.read_text(ALLOW_FILE)
        if cur and not cur.endswith("\n"):
            cur += "\n"
        settings.write_text(ALLOW_FILE, cur + d + "\n")
        blocklist.reload_local()
        return await _send(w, 200, "text/plain", "ok")
    if path == "/api/pause":
        try:
            dns.pause(max(0, min(86400, int(a.get("s", "0")))))
        except ValueError:
            return await _send(w, 400, "text/plain", "bad seconds")
        return await _send(w, 200, "text/plain", "ok")
    if path == "/api/update":
        asyncio.create_task(blocklist.update())
        return await _send(w, 200, "text/plain", "ok")
    if path == "/api/wifireset":
        settings.clear_wifi()
        _reboot_later(1000)
        return await _send(w, 200, "text/plain", "rebooting")
    return await _send(w, 404, "text/plain", "not found")


async def _setup(w, method, path, a, headers):
    if path == "/style.css":
        return await _file(w, "style.css", "text/css")
    if path == "/scan":
        seen = []
        try:
            for n in wlan.scan():
                ssid = n[0].decode() if isinstance(n[0], bytes) else n[0]
                if ssid and ssid not in seen:
                    seen.append(ssid)
        except Exception:
            pass
        return await _send(w, 200, "application/json", json.dumps(seen))
    if path == "/save" and method == "POST":
        if not a.get("ssid") or len(a.get("admin", "")) < 8:
            return await _send(w, 400, "text/plain", "SSID and an admin password of 8+ characters are required")
        s = settings.s
        s["ssid"], s["pw"], s["apass"] = a["ssid"], a.get("pass", ""), a["admin"]
        s["ip"], s["gw"], s["mask"] = a.get("ip", ""), a.get("gw", ""), a.get("mask", "")
        settings.save()
        _reboot_later(1500)
        return await _send(w, 200, "text/html",
                           "<meta name=viewport content='width=device-width'><link rel=stylesheet href=/style.css>"
                           "<main><h2>Saved</h2><p>adBlockr is restarting and joining your Wi-Fi. "
                           "Its IP address will show on the screen.</p></main>")
    return await _file(w, "setup.html", "text/html")   # captive portal: every other URL


async def _handle(r, w):
    try:
        line = await r.readline()
        if not line:
            return
        method, target, _ = line.decode().split(" ", 2)
        path, _, qs = target.partition("?")
        headers = {}
        while True:
            h = await r.readline()
            if h in (b"\r\n", b"\n", b""):
                break
            k, _, v = h.decode().partition(":")
            headers[k.strip().lower()] = v.strip()
        a = _form(qs)
        n = int(headers.get("content-length", "0") or 0)
        if n > MAX_BODY:
            return await _send(w, 400, "text/plain", "request too large")
        if n:
            a.update(_form((await r.readexactly(n)).decode()))
        await (_setup if _portal else _admin)(w, method, path, a, headers)
    except Exception as e:
        print("web:", repr(e))
    finally:
        try:
            w.close()
            await w.wait_closed()
        except Exception:
            pass


async def start(portal=False):
    global _portal
    _portal = portal
    return await asyncio.start_server(_handle, "0.0.0.0", 80, backlog=4)
