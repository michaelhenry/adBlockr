# Blocklist: two sorted uint32 tables holding independent 30-bit hashes of every domain.
# A name is blocked only if both hashes are present (false match ~1 in 2e8 lookups) at
# 8 bytes per domain. Updates download in the background and swap in when done; the
# tables are cached in flash so blocking works straight after a reboot.
import asyncio
import gc
import os
import ssl
import struct
from array import array
import settings
import tz
from config import *

try:
    from hashfn import fnv, has, SEED1, SEED2
except Exception:                       # no viper on this build
    from hashfn_py import fnv, has, SEED1, SEED2

_a = _b = bytearray()                   # live tables
_n = 0                                  # entries in _a (== domains)
_nb = 0                                 # entries in _b
allow, custom = set(), set()

status = {"state": "empty", "domains": 0, "progress": 0, "src": 0, "srcs": 0,
          "last": 0, "err": "", "updating": False, "cap": 0}


# --------------------------------------------------------------------------- parsing
def parse_line(s):
    """hosts ("0.0.0.0 ads.example.com"), plain domains, or "||ads.example.com^" -> domain or None."""
    i = s.find("#")
    if i >= 0:
        s = s[:i]
    s = s.strip()
    if not s or s[0] in "![@":
        return None
    if s.startswith("||"):
        t = s[2:]
        e = t.find("^")
        if e >= 0:
            if e + 1 < len(t):
                return None             # has modifiers after ^
            t = t[:e]
    else:
        parts = s.split()
        if parts[0] in ("0.0.0.0", "127.0.0.1", "::", "::1", "::0"):
            if len(parts) < 2:
                return None
            t = parts[1]
        else:
            t = parts[0]
    if t.startswith("*."):
        t = t[2:]
    t = t.rstrip(".").lower()
    if len(t) < 3 or len(t) > 253 or "." not in t or t.replace(".", "").isdigit():
        return None
    if t in ("localhost.localdomain", "broadcasthost"):
        return None
    return t


def _load_set(path):
    out = set()
    for ln in settings.read_text(path).split("\n"):
        d = parse_line(ln)
        if d:
            out.add(d)
    return out


def reload_local():
    global allow, custom
    allow, custom = _load_set(ALLOW_FILE), _load_set(BLOCK_FILE)


# --------------------------------------------------------------------------- lookup
def _hit(b, k, n):
    mv = memoryview(b)[k:]
    return has(_a, _n, fnv(mv, n - k, SEED1)) and has(_b, _nb, fnv(mv, n - k, SEED2))


def is_blocked(name):
    """name must be lowercase. Allowlist and custom list match the name and all parents."""
    if not name:
        return False
    b = name.encode()
    n, k, first, blocked = len(b), 0, True, False
    sub = settings.s["subdom"]
    while True:
        suf = name[k:]
        if suf in allow:
            return False
        if suf in custom:
            blocked = True
        if not blocked and _n and (first or sub) and "." in suf and _hit(b, k, n):
            blocked = True
        first = False
        j = name.find(".", k)
        if j < 0:
            return blocked
        k = j + 1


# --------------------------------------------------------------------------- cache
def _save(a, na, b, nb, when):
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, "wb") as f:
        f.write(struct.pack("<4sIII", b"ADB2", na, nb, when))
        f.write(a)
        f.write(b)
    os.rename(tmp, CACHE_FILE)


def _load():
    global _a, _b, _n, _nb
    try:
        with open(CACHE_FILE, "rb") as f:
            magic, na, nb, when = struct.unpack("<4sIII", f.read(16))
            if magic != b"ADB2":
                return False
            a, b = bytearray(na * 4), bytearray(nb * 4)
            if f.readinto(a) != na * 4 or f.readinto(b) != nb * 4:
                return False
    except (OSError, ValueError, MemoryError):
        return False
    _a, _b, _n, _nb = a, b, na, nb
    status.update(domains=na, last=when, state="ready")
    return True


def init():
    reload_local()
    if not _load():
        status["state"] = "empty"


# --------------------------------------------------------------------------- download
async def _fetch(url, on_line):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.verify_mode = ssl.CERT_NONE     # a tampered list can only change what gets blocked
    for _ in range(5):                  # follow up to 4 redirects
        proto, _, hostport, path = (url.split("/", 3) + [""])[:4]
        https = proto == "https:"
        host, _, port = hostport.partition(":")
        port = int(port) if port else (443 if https else 80)
        r, w = await asyncio.open_connection(host, port, ssl=ctx if https else None)
        try:
            w.write(("GET /%s HTTP/1.1\r\nHost: %s\r\nUser-Agent: adblockr/%s\r\n"
                     "Accept-Encoding: identity\r\nConnection: close\r\n\r\n" % (path, host, VERSION)).encode())
            await w.drain()
            code = int((await r.readline()).split()[1])
            chunked, loc = False, None
            while True:
                h = await r.readline()
                if h in (b"\r\n", b"\n", b""):
                    break
                k, _, v = h.decode().partition(":")
                k, v = k.strip().lower(), v.strip()
                if k == "transfer-encoding" and "chunked" in v.lower():
                    chunked = True
                elif k == "location":
                    loc = v
            if code in (301, 302, 303, 307, 308) and loc:
                url = loc if loc.startswith("http") else proto + "//" + hostport + loc
                continue
            if code != 200:
                raise OSError("HTTP %d %s" % (code, url))
            if chunked:
                carry = b""
                while True:
                    n = int((await r.readline()).decode().split(";")[0].strip(), 16)
                    if n == 0:
                        break
                    data = carry + await r.readexactly(n)
                    await r.readexactly(2)
                    lines = data.split(b"\n")
                    carry = lines.pop()
                    for ln in lines:
                        on_line(ln)
                    await asyncio.sleep(0)
                if carry:
                    on_line(carry)
            else:                       # 4 KB reads: one await per block, not per line
                carry = b""
                while True:
                    data = await r.read(4096)
                    if not data:
                        break
                    lines = (carry + data).split(b"\n")
                    carry = lines.pop()
                    for ln in lines:
                        on_line(ln)
                if carry:
                    on_line(carry)
            return
        finally:
            w.close()
            try:
                await w.wait_closed()
            except Exception:
                pass
    raise OSError("too many redirects")


async def _pack(arr):
    l = sorted(arr)
    out, prev = array("I"), -1
    for i, v in enumerate(l):
        if v != prev:
            out.append(v)
            prev = v
        if i % 4000 == 0:
            await asyncio.sleep(0)
    return bytearray(out), len(out)


async def update():
    """Download every list, then swap the new tables in. No-op if one is already running."""
    global _a, _b, _n, _nb
    if status["updating"]:
        return
    status.update(updating=True, state="downloading", progress=0, err="")
    try:
        gc.collect()
        cap = max(10000, gc.mem_free() // 32)   # tables + sort scratch; leaves headroom for TLS
        status["cap"] = cap
        A, B = array("I"), array("I")
        full = [False]

        def on_line(ln):
            if len(A) >= cap:
                full[0] = True
                return
            try:
                d = parse_line(ln.decode())
            except Exception:
                return
            if d:
                b = d.encode()
                A.append(fnv(b, len(b), SEED1))
                B.append(fnv(b, len(b), SEED2))
                status["progress"] = len(A)

        urls = [u.strip() for u in settings.read_text(LISTS_FILE, DEFAULT_LISTS).split("\n")]
        urls = [u for u in urls if u and not u.startswith("#")]
        status["srcs"], ok = len(urls), 0
        for i, u in enumerate(urls):
            status["src"] = i + 1
            try:
                await _fetch(u, on_line)
                ok += 1
            except Exception as e:
                status["err"] = str(e) or repr(e)
            if full[0]:
                status["err"] = "list truncated at %d domains (memory)" % cap
                break
        if not ok or not A:
            status["err"] = status["err"] or "no domains downloaded"
            status["state"] = "ready" if _n else "error"
            return
        a, na = await _pack(A)
        A = None                        # free it before sorting B (on_line still closes over A)
        b, nb = await _pack(B)
        B = None
        _a, _b, _n, _nb = a, b, na, nb
        when = tz.now() if tz.clock_set() else 0
        status.update(domains=na, last=when, state="ready")
        gc.collect()
        try:
            _save(a, na, b, nb, when)
        except OSError as e:
            status["err"] = "cache not saved: %s" % e
    finally:
        status["updating"] = False


# --------------------------------------------------------------------------- self-check
def _selftest():
    assert parse_line("0.0.0.0 ads.example.com # x") == "ads.example.com"
    assert parse_line("||Track.Example.org^") == "track.example.org"
    assert parse_line("||a.example.org^$third-party") is None
    assert parse_line("0.0.0.0 0.0.0.0") is None
    assert parse_line("example.net.") == "example.net"
    assert fnv(b"abc", 3, SEED1) != fnv(b"abc", 3, SEED2)
    t = bytearray(array("I", [3, 7, 9]))
    assert has(t, 3, 7) and not has(t, 3, 8)
