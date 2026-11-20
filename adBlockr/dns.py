# UDP DNS sinkhole + forwarder.
#  - blocked A -> 0.0.0.0, blocked AAAA -> ::, other blocked types -> NODATA
#  - local names (*.lan, *.home.arpa, single-label, private-range PTR) -> router
#  - everything else -> upstream 1, retried on upstream 2
# Answers only clients on its own subnet, so it is never an open resolver.
import asyncio
import os
import socket
import struct
import time
from asyncio import core
import blocklist
import settings
import stats
from config import *

_srv = _up = None
_pending = {}            # new id -> [orig id, client addr, t0, tries, local, sent to, query]
_paused_until = 0        # ticks_ms deadline, 0 = not paused
_net = [0, 0, "", ""]    # my ip int, mask int, gateway, my ip str
_ups = [DEFAULT_UPSTREAM1, DEFAULT_UPSTREAM2]
on_block = None          # optional callback (LED flash)


def _readable(s):
    yield core._io_queue.queue_read(s)   # wake this task when s has data (as asyncio streams do)


def ip2int(s):
    a = s.split(".")
    return (int(a[0]) << 24) | (int(a[1]) << 16) | (int(a[2]) << 8) | int(a[3])


def set_network(ip, mask, gw):
    _net[0], _net[1], _net[2], _net[3] = ip2int(ip), ip2int(mask), gw, ip


def reload_upstreams():
    _ups[0] = settings.s["up1"] or DEFAULT_UPSTREAM1
    _ups[1] = settings.s["up2"] or _ups[0]


def pause(seconds):
    global _paused_until
    _paused_until = (time.ticks_add(time.ticks_ms(), seconds * 1000) | 1) if seconds else 0


def paused():
    global _paused_until
    if _paused_until and time.ticks_diff(_paused_until, time.ticks_ms()) <= 0:
        _paused_until = 0
    return _paused_until != 0


def pause_remaining():
    return time.ticks_diff(_paused_until, time.ticks_ms()) // 1000 if paused() else 0


# --------------------------------------------------------------------------- packets
def parse_q(p):
    """-> (lowercase name, qtype, end of question) or None for anything but a plain query."""
    n = len(p)
    if n < 12 or p[2] & 0x80 or (p[2] >> 3) & 0x0F or ((p[4] << 8) | p[5]) != 1:
        return None
    i, labels = 12, []
    while True:
        if i >= n:
            return None
        l = p[i]
        i += 1
        if l == 0:
            break
        if l & 0xC0 or i + l > n:
            return None
        labels.append(bytes(p[i:i + l]))
        i += l
    if i + 4 > n:
        return None
    try:
        name = b".".join(labels).decode().lower()
    except Exception:
        name = "?"
    return name, (p[i] << 8) | p[i + 1], i + 4


def is_local(n):
    if not n:
        return False
    if "." not in n:
        return True                                     # single label
    for suf in (".lan", ".home.arpa", ".internal", ".localdomain", ".10.in-addr.arpa", ".168.192.in-addr.arpa"):
        if n.endswith(suf):
            return True
    if n.endswith(".172.in-addr.arpa"):                 # 172.16.0.0/12
        parts = n.split(".")
        try:
            return 16 <= int(parts[-4]) <= 31
        except (ValueError, IndexError):
            return False
    return False


def synth(q, qend, qtype, ans, ttl):
    out = bytearray(q[:qend])
    out[2] = 0x80 | (q[2] & 0x01)                       # QR=1, RD copied
    out[3] = 0x80                                       # RA=1, NOERROR
    out[4:12] = bytes([0, 1, 0, 1 if ans else 0, 0, 0, 0, 0])   # drop NS / AR (incl. OPT)
    if ans:
        out += b"\xc0\x0c" + struct.pack(">HHIH", qtype, 1, ttl, len(ans)) + ans
    return out


def servfail(q, qend):
    out = bytearray(q[:qend])
    out[2] = 0x80 | (q[2] & 0x01)
    out[3] = 0x82
    out[6:12] = bytes(6)
    return out


def _send(sock, data, addr):
    try:
        sock.sendto(data, addr)
    except OSError:
        pass                                            # buffer full: the client retries


# --------------------------------------------------------------------------- forwarding
def _forward(q, addr, local):
    while True:
        nid = int.from_bytes(os.urandom(2), "big")
        if nid not in _pending:
            break
    if len(_pending) >= PENDING_MAX:                    # table full: drop the oldest
        old = min(_pending, key=lambda k: _pending[k][2])
        del _pending[old]
        stats.fail()
    dest = _net[2] if local else _ups[0]
    _pending[nid] = [(q[0] << 8) | q[1], addr, time.ticks_ms(), 1, local, dest, bytes(q)]
    pkt = bytearray(q)
    pkt[0], pkt[1] = nid >> 8, nid & 0xFF
    _send(_up, pkt, (dest, 53))


def _query(q, addr):
    ip = addr[0]
    try:
        if (ip2int(ip) & _net[1]) != (_net[0] & _net[1]):
            return
    except (ValueError, IndexError):
        return
    r = parse_q(q)
    if not r:
        return
    name, qt, qend = r
    if name in (HOSTNAME, HOSTNAME + ".lan") and qt == 1:
        _send(_srv, synth(q, qend, qt, bytes(int(x) for x in _net[3].split(".")), 300), addr)
        stats.record(name, ip, qt, 2)
        return
    local = settings.s["local"] and is_local(name)
    if not local and not paused() and blocklist.is_blocked(name):
        ans = bytes(4) if qt == 1 else bytes(16) if qt == 28 else None
        _send(_srv, synth(q, qend, qt, ans, BLOCKED_TTL), addr)
        stats.record(name, ip, qt, 1)
        if on_block:
            on_block()
        return
    _forward(q, addr, local)
    stats.record(name, ip, qt, 2 if local else 0)


def _answer(d, addr):
    if len(d) < 12:
        return
    e = _pending.get((d[0] << 8) | d[1])
    if not e or addr[0] != e[5]:                        # unknown id or spoofed source
        return
    out = bytearray(d)
    out[0], out[1] = e[0] >> 8, e[0] & 0xFF
    _send(_srv, out, e[1])
    stats.latency(time.ticks_diff(time.ticks_ms(), e[2]))
    del _pending[(d[0] << 8) | d[1]]


def _udp(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.setblocking(False)
    return s


async def _drain(sock, handler):
    while True:
        await _readable(sock)
        for _ in range(16):
            try:
                d, a = sock.recvfrom(1500)
            except OSError:
                break
            try:
                handler(d, a)
            except Exception as e:                      # one bad packet must not stop DNS
                print("dns:", repr(e))


async def _sweep():
    while True:
        await asyncio.sleep_ms(100)
        now = time.ticks_ms()
        for k in list(_pending):
            e = _pending[k]
            age = time.ticks_diff(now, e[2])
            if e[3] == 1 and age > UPSTREAM_RETRY_MS and not e[4] and _ups[1] != _ups[0]:
                e[3], e[5] = 2, _ups[1]
                pkt = bytearray(e[6])
                pkt[0], pkt[1] = k >> 8, k & 0xFF
                _send(_up, pkt, (e[5], 53))
            elif age > UPSTREAM_TIMEOUT_MS:
                r = parse_q(e[6])
                if r:
                    _send(_srv, servfail(e[6], r[2]), e[1])
                stats.fail()
                del _pending[k]


def start():
    """Create the DNS tasks (call inside the running asyncio loop)."""
    global _srv, _up
    reload_upstreams()
    _srv = _udp(DNS_PORT)
    _up = _udp(0)                                       # any free source port for upstream queries
    asyncio.create_task(_drain(_srv, _query))
    asyncio.create_task(_drain(_up, _answer))
    asyncio.create_task(_sweep())


async def captive(ap_ip):
    """Setup hotspot: answer every A query with our own address so phones open the portal."""
    s = _udp(DNS_PORT)
    me = bytes(int(x) for x in ap_ip.split("."))

    def h(q, addr):
        r = parse_q(q)
        if r:
            _send(s, synth(q, r[2], r[1], me if r[1] == 1 else None, 10), addr)

    await _drain(s, h)
