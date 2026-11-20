# Query counters, per-minute history, top blocked domains and a recent-query log.
import time
import tz
import settings

HIST_MIN = 60
LOG_SIZE = 40
TOP_SIZE = 20

queries = blocked = forwarded = failed = 0        # since local midnight (or boot)
total_queries = total_blocked = 0                 # since boot
avg_latency = 0
last_blocked = ""
_hist_q = [0] * HIST_MIN
_hist_b = [0] * HIST_MIN
_hist_m = [-1] * HIST_MIN
top = {}                                          # name -> count (space-saving, max TOP_SIZE)
log = []                                          # oldest first: (t, name, client, qtype, result)
_last_day = -1

QTYPES = {1: "A", 28: "AAAA", 5: "CNAME", 12: "PTR", 15: "MX", 16: "TXT", 33: "SRV",
          64: "SVCB", 65: "HTTPS", 2: "NS", 6: "SOA"}


def _minute():
    return time.ticks_ms() // 60000


def record(name, client, qtype, result):
    """result: 0 forwarded, 1 blocked, 2 local, 3 failed."""
    global queries, blocked, forwarded, total_queries, total_blocked, last_blocked
    queries += 1
    total_queries += 1
    is_b = result == 1
    if is_b:
        blocked += 1
        total_blocked += 1
        last_blocked = name
        if name in top:
            top[name] += 1
        elif len(top) < TOP_SIZE:
            top[name] = 1
        else:                                     # replace the least counted entry
            k = min(top, key=top.get)
            top[name] = top.pop(k) + 1
    elif result in (0, 2):
        forwarded += 1
    m = _minute()
    i = m % HIST_MIN
    if _hist_m[i] != m:
        _hist_m[i], _hist_q[i], _hist_b[i] = m, 0, 0
    _hist_q[i] += 1
    if is_b:
        _hist_b[i] += 1
    log.append((tz.now(), name, client, qtype, result))
    if len(log) > LOG_SIZE:
        log.pop(0)


def fail():
    global failed
    failed += 1


def latency(ms):
    global avg_latency
    avg_latency = (avg_latency * 7 + ms) // 8 if avg_latency else ms


def tick():
    """Once a second: reset the daily counters at local midnight."""
    global queries, blocked, forwarded, failed, _last_day
    if not tz.clock_set():
        return
    yday = tz.localtime(settings.s["tz"])[7]
    if _last_day >= 0 and yday != _last_day:
        queries = blocked = forwarded = failed = 0
        top.clear()
    _last_day = yday


def pct():
    return (blocked * 100 + queries // 2) // queries if queries else 0


def history(i):
    """(queries, blocked) for minute i, 0 = oldest, HIST_MIN-1 = now."""
    m = _minute() - (HIST_MIN - 1 - i)
    j = m % HIST_MIN
    return (_hist_q[j], _hist_b[j]) if _hist_m[j] == m else (0, 0)


def qtype_name(t):
    return QTYPES.get(t, "?")
