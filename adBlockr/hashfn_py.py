# Pure-Python twin of hashfn.py (same results, slower). Used only if viper is unavailable.
import struct

SEED1 = 0x1C9DC5
SEED2 = 0x2B3F17


def fnv(b, n, seed):
    h = seed
    for i in range(n):
        h = ((h ^ b[i]) * 16777619) & 0xFFFFFFFF
    return h & 0x3FFFFFFF


def has(table, n, h):
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) >> 1
        if struct.unpack_from("<I", table, mid * 4)[0] < h:
            lo = mid + 1
        else:
            hi = mid
    return lo < n and struct.unpack_from("<I", table, lo * 4)[0] == h
