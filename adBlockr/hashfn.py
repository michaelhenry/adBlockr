# Fast helpers for the blocklist, compiled to machine code with viper.
# blocklist.py falls back to hashfn_py.py if this build has no native emitter.
import micropython

SEED1 = 0x1C9DC5
SEED2 = 0x2B3F17


@micropython.viper
def fnv(b, n: int, seed: int) -> int:
    """FNV-1a over the first n bytes of b, folded to 30 bits (stays a small int)."""
    p = ptr8(b)
    h = uint(seed)
    i = 0
    while i < n:
        h = (h ^ uint(p[i])) * uint(16777619)
        i += 1
    return int(h & uint(0x3FFFFFFF))


@micropython.viper
def has(table, n: int, h: int) -> bool:
    """Binary search a sorted uint32 table (bytearray) of n entries."""
    a = ptr32(table)
    lo = 0
    hi = n
    while lo < hi:
        mid = (lo + hi) >> 1
        if a[mid] < h:
            lo = mid + 1
        else:
            hi = mid
    return lo < n and a[lo] == h
