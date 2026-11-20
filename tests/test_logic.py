import sys, types, time, calendar, struct
import os
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "adBlockr"))
# stubs for MicroPython-only modules
time.ticks_ms = lambda: int(time.monotonic()*1000)
time.ticks_diff = lambda a, b: a - b
time.ticks_add = lambda a, b: a + b
import asyncio
asyncio.core = types.SimpleNamespace(_io_queue=None); sys.modules['asyncio.core'] = asyncio.core
import hashfn_py as H
sys.modules['hashfn'] = H              # viper version is checked by mpy-cross; same algorithm
import settings, blocklist, dns, tz, stats
blocklist._selftest()
# lookup with real tables
from array import array
doms = ["ads.example.com", "tracker.net", "x.y.z.org"]
A = sorted(H.fnv(d.encode(), len(d), H.SEED1) for d in doms)
B = sorted(H.fnv(d.encode(), len(d), H.SEED2) for d in doms)
blocklist._a, blocklist._b = bytearray(array("I", A)), bytearray(array("I", B)); blocklist._n = blocklist._nb = 3
settings.s["subdom"] = False
assert blocklist.is_blocked("ads.example.com") and not blocklist.is_blocked("example.com")
assert not blocklist.is_blocked("sub.ads.example.com")
settings.s["subdom"] = True
assert blocklist.is_blocked("sub.ads.example.com")
blocklist.allow = {"tracker.net"}; assert not blocklist.is_blocked("tracker.net")
blocklist.custom = {"evil.com"}; assert blocklist.is_blocked("a.evil.com")
# DNS packet round trip
q = bytes.fromhex("abcd01000001000000000000") + b"\x03ads\x07example\x03com\x00" + b"\x00\x01\x00\x01"
name, qt, end = dns.parse_q(q); assert (name, qt, end) == ("ads.example.com", 1, len(q))
r = dns.synth(q, end, 1, bytes(4), 60)
assert r[:2] == q[:2] and r[2] & 0x80 and r[7] == 1 and r[-4:] == bytes(4) and struct.unpack(">I", r[-10:-6])[0] == 60
assert dns.servfail(q, end)[3] & 0x0F == 2
assert dns.is_local("printer") and dns.is_local("nas.lan") and dns.is_local("5.20.172.in-addr.arpa") and not dns.is_local("1.40.172.in-addr.arpa") and not dns.is_local("google.com")
# time zones (CPython epoch 1970 == MicroPython 1.29 esp32? EPOCH handles either)
mel = "AEST-10AEDT,M10.1.0,M4.1.0/3"
jan = calendar.timegm((2026, 1, 15, 0, 0, 0)); jul = calendar.timegm((2026, 7, 15, 0, 0, 0))
assert tz.offset(mel, jan) == 11*3600 and tz.offset(mel, jul) == 10*3600, (tz.offset(mel, jan), tz.offset(mel, jul))
ny = "EST5EDT,M3.2.0,M11.1.0"
assert tz.offset(ny, jan) == -5*3600 and tz.offset(ny, jul) == -4*3600
assert tz.offset("UTC0", jan) == 0 and tz.offset("<+08>-8", jan) == 8*3600
# 2026 Melbourne DST starts Sun 4 Oct 02:00 local (= 3 Oct 16:00 UTC)
t = calendar.timegm((2026, 10, 3, 16, 0, 0))
assert tz.offset(mel, t - 60) == 10*3600 and tz.offset(mel, t + 60) == 11*3600
# stats
stats.record("a.com", "192.168.1.5", 1, 1); stats.record("b.com", "192.168.1.5", 28, 0)
assert stats.queries == 2 and stats.blocked == 1 and stats.pct() == 50 and stats.history(59) == (2, 1)
print("all logic tests passed")
