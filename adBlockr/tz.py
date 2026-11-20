# Unix time and POSIX TZ strings ("AEST-10AEDT,M10.1.0,M4.1.0/3") without a C library.
import time

# MicroPython ports differ on the epoch (1970 or 2000); everything here is Unix time.
EPOCH = 946684800 if time.gmtime(0)[0] == 2000 else 0


def now():
    return time.time() + EPOCH


def clock_set():
    return now() > 1700000000


def _num(s, i):
    j = i
    while j < len(s) and (s[j].isdigit() or s[j] in "+-:"):
        j += 1
    return s[i:j], j


def _hms(t):
    neg = t.startswith("-")
    parts = [int(p) for p in t.lstrip("+-").split(":")] + [0, 0]
    v = parts[0] * 3600 + parts[1] * 60 + parts[2]
    return -v if neg else v


def _name(s, i):
    if i < len(s) and s[i] == "<":
        return s.index(">", i) + 1
    while i < len(s) and s[i].isalpha():
        i += 1
    return i


def _parse(tzs):
    """-> (std_offset_s, dst_offset_s or None, start_rule, end_rule). Offsets are east of UTC."""
    i = _name(tzs, 0)
    off, i = _num(tzs, i)
    std = -_hms(off) if off else 0
    if i >= len(tzs):
        return std, None, None, None
    j = _name(tzs, i)
    if j == i:
        return std, None, None, None
    off, j = _num(tzs, j)
    dst = -_hms(off) if off else std + 3600
    rules = tzs[j:].lstrip(",").split(",")
    if len(rules) != 2:
        return std, None, None, None
    return std, dst, rules[0], rules[1]


def _days_in_month(y, m):
    if m == 2:
        return 29 if (y % 4 == 0 and (y % 100 or y % 400 == 0)) else 28
    return 31 if m in (1, 3, 5, 7, 8, 10, 12) else 30


def _days(y, m, d):
    """Days since 1970-01-01 (proleptic Gregorian), no mktime needed."""
    y -= m <= 2
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    return era * 146097 + yoe * 365 + yoe // 4 - yoe // 100 + doy - 719468


def _rule_time(rule, year, offset):
    """UTC unix time when 'Mm.w.d[/time]' happens in year, given the offset in force before it."""
    r, _, t = rule.partition("/")
    secs = _hms(t) if t else 7200
    m, w, d = (int(x) for x in r[1:].split("."))   # shortcut: only the M form; Jn/n rules are rare
    days = _days(year, m, 1)
    first = days * 86400
    wd_first = (days + 4) % 7                       # 1970-01-01 was a Thursday; 0 = Sunday
    day = 1 + (d - wd_first) % 7 + (w - 1) * 7
    if w == 5:
        while day > _days_in_month(year, m):
            day -= 7
    return first + (day - 1) * 86400 + secs - offset


_cache = [None, None]


def offset(tzs, utc):
    if _cache[0] != tzs:
        try:
            _cache[1] = _parse(tzs)
        except Exception:
            _cache[1] = (0, None, None, None)
        _cache[0] = tzs
    std, dst, start, end = _cache[1]
    if dst is None:
        return std
    try:
        y = time.gmtime(utc - EPOCH)[0]
        a, b = _rule_time(start, y, std), _rule_time(end, y, dst)
        on = (a <= utc < b) if a < b else not (b <= utc < a)   # southern hemisphere wraps the year
        return dst if on else std
    except Exception:
        return std


def localtime(tzs, utc=None):
    utc = now() if utc is None else utc
    return time.gmtime(utc + offset(tzs, utc) - EPOCH)
