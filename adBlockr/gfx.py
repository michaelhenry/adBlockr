# ST7789 display + XPT2046 touch for the NM-CYD-C5, drawn through one full-screen framebuf.
# Drawing marks a dirty row band; show() pushes just those rows over SPI.
import framebuf
import math
import struct
import time
from array import array
from machine import Pin, SPI, PWM
from config import *

W, H = 320, 240


def rgb(r, g, b):
    """RGB888 -> RGB565, byte-swapped because the panel wants big-endian pixels."""
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c & 0xFF) << 8) | (c >> 8)


def _unswap(c):
    return ((c & 0xFF) << 8) | (c >> 8)


def blend(fg, bg, a):
    """Mix two swapped colours, a = 0..15 (15 = fg)."""
    f, b = _unswap(fg), _unswap(bg)
    r = ((f >> 11) * a + (b >> 11) * (15 - a)) // 15
    g = (((f >> 5) & 63) * a + ((b >> 5) & 63) * (15 - a)) // 15
    bl = ((f & 31) * a + (b & 31) * (15 - a)) // 15
    c = (r << 11) | (g << 5) | bl
    return ((c & 0xFF) << 8) | (c >> 8)


class Font:
    """4-bit anti-aliased bitmap font made by tools/make_fonts.py."""

    def __init__(self, path):
        with open(path, "rb") as f:
            d = bytearray(f.read())
        assert d[:3] == b"AF1", path
        self.h, self.first, n = d[3], d[5], d[6]   # d[4] = ascent, unused
        mv = memoryview(d)
        self.adv = bytearray(n)
        self.glyph = []
        for i in range(n):
            adv, off = struct.unpack_from("<BI", d, 7 + i * 5)
            self.adv[i] = adv
            size = ((adv + 1) // 2) * self.h
            self.glyph.append(framebuf.FrameBuffer(mv[off:off + size], adv, self.h, framebuf.GS4_HMSB) if adv else None)
        self._d = d                     # keep the buffer alive

    def width(self, s):
        w, f, n = 0, self.first, len(self.adv)
        for ch in s:
            i = ord(ch) - f
            if 0 <= i < n:
                w += self.adv[i]
        return w


class Display:
    def __init__(self):
        self.spi = SPI(1, baudrate=SPI_HZ, sck=Pin(PIN_SCK), mosi=Pin(PIN_MOSI), miso=Pin(PIN_MISO))
        self.cs = Pin(PIN_TFT_CS, Pin.OUT, value=1)
        self.dc = Pin(PIN_TFT_DC, Pin.OUT, value=0)
        self.tcs = Pin(PIN_TOUCH_CS, Pin.OUT, value=1)
        self.bl = PWM(Pin(PIN_BL), freq=5000, duty_u16=0)
        self.buf = bytearray(W * H * 2)
        self.fb = framebuf.FrameBuffer(self.buf, W, H, framebuf.RGB565)
        self._pal = {}
        self.y0, self.y1 = 0, H
        self._fast_clk = self._probe_clock()
        for c, d, ms in ((0x01, None, 150), (0x11, None, 120), (0x3A, b"\x55", 0),
                         (0x36, bytes([MADCTL]), 0), (0x20, None, 0), (0x13, None, 0), (0x29, None, 20)):
            self._cmd(c, d)
            time.sleep_ms(ms)

    # ---------------------------------------------------------------- SPI
    def _cmd(self, c, data=None):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([c]))
        if data:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def dirty(self, y, h):
        if y < self.y0:
            self.y0 = y
        if y + h > self.y1:
            self.y1 = y + h

    def show(self):
        y0, y1 = max(0, self.y0), min(H, self.y1)
        self.y0, self.y1 = H, 0
        if y1 <= y0:
            return
        self._cmd(0x2A, struct.pack(">HH", 0, W - 1))
        self._cmd(0x2B, struct.pack(">HH", y0, y1 - 1))
        self.cs(0)
        self.dc(0)
        self.spi.write(b"\x2C")
        self.dc(1)
        self.spi.write(memoryview(self.buf)[y0 * W * 2:y1 * W * 2])
        self.cs(1)

    def brightness(self, v):
        self.bl.duty_u16(max(0, min(255, v)) * 257)

    # ---------------------------------------------------------------- shapes
    def fill(self, c):
        self.fb.fill(c)
        self.dirty(0, H)

    def rect(self, x, y, w, h, c):
        self.fb.fill_rect(x, y, w, h, c)
        self.dirty(y, h)

    def hline(self, x, y, w, c):
        self.fb.hline(x, y, w, c)
        self.dirty(y, 1)

    def vline(self, x, y, h, c):
        self.fb.vline(x, y, h, c)
        self.dirty(y, h)

    def line(self, x0, y0, x1, y1, c):
        self.fb.line(x0, y0, x1, y1, c)
        self.dirty(min(y0, y1), abs(y1 - y0) + 1)

    def circle(self, x, y, r, c):
        self.fb.ellipse(x, y, r, r, c, True)
        self.dirty(y - r, 2 * r + 1)

    def rrect(self, x, y, w, h, r, c):
        r = min(r, w // 2, h // 2)
        fb = self.fb
        fb.fill_rect(x + r, y, w - 2 * r, h, c)
        fb.fill_rect(x, y + r, r, h - 2 * r, c)
        fb.fill_rect(x + w - r, y + r, r, h - 2 * r, c)
        if r:
            fb.ellipse(x + r, y + r, r, r, c, True, 2)
            fb.ellipse(x + w - r - 1, y + r, r, r, c, True, 1)
            fb.ellipse(x + r, y + h - r - 1, r, r, c, True, 4)
            fb.ellipse(x + w - r - 1, y + h - r - 1, r, r, c, True, 8)
        self.dirty(y, h)

    def poly(self, pts, c):
        ys = pts[1::2]
        self.fb.poly(0, 0, array("h", pts), c, True)
        self.dirty(min(ys), max(ys) - min(ys) + 1)

    def tri(self, x0, y0, x1, y1, x2, y2, c):
        self.poly([x0, y0, x1, y1, x2, y2], c)

    def wline(self, x0, y0, x1, y1, t, c):
        """Line t px thick with round ends."""
        dx, dy = x1 - x0, y1 - y0
        L = math.sqrt(dx * dx + dy * dy) or 1
        ox, oy = -dy / L * t / 2, dx / L * t / 2
        self.poly([round(x0 + ox), round(y0 + oy), round(x1 + ox), round(y1 + oy),
                   round(x1 - ox), round(y1 - oy), round(x0 - ox), round(y0 - oy)], c)
        r = t // 2
        self.circle(x0, y0, r, c)
        self.circle(x1, y1, r, c)

    def arc(self, cx, cy, r, t, a0, a1, c):
        """Thick arc. Angles in degrees, 0 = 6 o'clock, clockwise (TFT_eSPI convention)."""
        if a1 < a0:
            a1 += 360
        rr = max(1, t // 2)
        a = a0
        while a <= a1:
            th = math.radians(a)
            self.fb.ellipse(round(cx - r * math.sin(th)), round(cy + r * math.cos(th)), rr, rr, c, True)
            a += 6
        self.dirty(cy - r - rr, 2 * (r + rr) + 1)

    # ---------------------------------------------------------------- text
    def _palette(self, fg, bg):
        k = (fg << 16) | bg
        p = self._pal.get(k)
        if p is None:
            if len(self._pal) > 24:
                self._pal.clear()
            p = framebuf.FrameBuffer(bytearray(32), 16, 1, framebuf.RGB565)
            for i in range(16):
                p.pixel(i, 0, blend(fg, bg, i))
            self._pal[k] = p
        return p

    def text(self, s, x, y, font, fg, bg, align="l", clear=0):
        """Draw s with its line box top at y; align l/c/r relative to x.
        clear > 0 first fills a band that wide (aligned the same way) with bg."""
        w = font.width(s)
        if align == "c":
            x -= w // 2
        elif align == "r":
            x -= w
        if clear:
            cx = x if align == "l" else (x + w // 2 - clear // 2 if align == "c" else x + w - clear)
            self.fb.fill_rect(cx, y, clear, font.h, bg)
        pal = self._palette(fg, bg)
        f, n, adv, g = font.first, len(font.adv), font.adv, font.glyph
        blit = self.fb.blit
        for ch in s:
            i = ord(ch) - f
            if 0 <= i < n and adv[i]:
                if g[i] is not None:
                    blit(g[i], x, y, 0, pal)
                x += adv[i]
        self.dirty(y, font.h)
        return w

    # ---------------------------------------------------------------- touch
    # Display and touch share one SPI bus at different clocks. spi.init(baudrate=...) rebuilds
    # the bus (~25 ms each way), which would stall DNS on every touch poll. Instead we swap
    # the ESP32-C5 GPSPI2 clock-divider register directly (µs); IDF applies it at the next
    # transfer. shortcut: chip-specific; _probe_clock() checks it and falls back to spi.init.
    _CLK_REG = 0x60081000 + 0x0C        # GPSPI2 SPI_CLOCK_REG on ESP32-C5

    def _probe_clock(self):
        try:
            import machine
            self.spi.init(baudrate=TOUCH_HZ)
            self.spi.write(b"\x00")
            slow = machine.mem32[self._CLK_REG]
            self.spi.init(baudrate=SPI_HZ)
            self.spi.write(b"\x00")
            fast = machine.mem32[self._CLK_REG]
            if slow != fast and fast == machine.mem32[self._CLK_REG]:
                self._clk = (slow, fast)
                return True
        except Exception:
            pass
        self.spi.init(baudrate=SPI_HZ)
        return False

    def _touch_clock(self, on):
        if self._fast_clk:
            import machine
            machine.mem32[self._CLK_REG] = self._clk[0] if on else self._clk[1]
        else:
            self.spi.init(baudrate=TOUCH_HZ if on else SPI_HZ)

    def touch_raw(self):
        """(x, y, z) raw 12-bit XPT2046 readings; z > 600 means pressed."""
        spi = self.spi
        self._touch_clock(True)
        self.tcs(0)
        buf = bytearray(2)

        def rd(cmd):
            spi.write(bytes([cmd]))
            spi.readinto(buf)
            return ((buf[0] << 8) | buf[1]) >> 3

        z = 4095 + rd(0xB1) - rd(0xC1)
        xs, ys = [], []
        if z > 300:
            for _ in range(5):
                xs.append(rd(0xD1))
                ys.append(rd(0x91))
        rd(0x90)                        # leave the ADC powered down
        self.tcs(1)
        self._touch_clock(False)
        if not xs:
            return 0, 0, 0
        xs.sort()
        ys.sort()
        return xs[2], ys[2], z          # median of 5
