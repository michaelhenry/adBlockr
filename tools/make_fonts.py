"""Render Inter (SIL OFL) into 4-bit anti-aliased bitmap fonts for adBlockr.

Run on a computer (needs Pillow), not on the board:
    python3 tools/make_fonts.py path/to/Inter-ttf-folder

Output: adBlockr/fonts/{s,m,b}.fnt

File layout (little-endian):
    b"AF1"  u8 height  u8 ascent  u8 first  u8 count
    count x (u8 advance, u32 offset)      offset is from the start of the file
    glyph bitmaps: framebuf GS4_HMSB, advance x height, 2 px per byte, rows padded to a byte
"""
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "adBlockr", "fonts")

# name, ttf file, pixel size, characters
FONTS = [
    ("s", "Inter-Regular.ttf", 14, "".join(chr(c) for c in range(32, 127))),   # body / labels
    ("m", "Inter-Bold.ttf", 22, "".join(chr(c) for c in range(32, 127))),      # titles
    ("b", "Inter-Bold.ttf", 46, " ,-.%0123456789:"),                            # hero number
]


def render(ttf, size, chars):
    font = ImageFont.truetype(ttf, size)
    ascent, descent = font.getmetrics()
    height = ascent + descent
    glyphs = []
    for ch in chars:
        adv = max(1, round(font.getlength(ch)))
        img = Image.new("L", (adv, height), 0)
        ImageDraw.Draw(img).text((0, 0), ch, font=font, fill=255)
        rowbytes = (adv + 1) // 2
        data = bytearray(rowbytes * height)
        px = img.load()
        for y in range(height):
            for x in range(adv):
                v = px[x, y] >> 4            # 0..15
                i = y * rowbytes + x // 2
                data[i] |= v << 4 if x % 2 == 0 else v   # HMSB: left pixel in the high nibble
        glyphs.append((adv, bytes(data)))
    return height, ascent, glyphs


def pack(height, ascent, first, glyphs):
    head = b"AF1" + bytes([height, ascent, first, len(glyphs)])
    off = len(head) + len(glyphs) * 5
    table, blob = b"", b""
    for adv, data in glyphs:
        table += struct.pack("<BI", adv, off + len(blob))
        blob += data
    return head + table + blob


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(OUT, exist_ok=True)
    for name, ttf, size, chars in FONTS:
        # the file format needs one contiguous range; gaps become zero-width glyphs
        first, last = ord(min(chars)), ord(max(chars))
        full = "".join(chr(c) for c in range(first, last + 1))
        height, ascent, glyphs = render(os.path.join(src, ttf), size, full)
        glyphs = [g if full[i] in chars else (0, b"") for i, g in enumerate(glyphs)]
        data = pack(height, ascent, first, glyphs)
        with open(os.path.join(OUT, name + ".fnt"), "wb") as f:
            f.write(data)
        print(name, ttf, size, "px: height", height, "ascent", ascent, len(data), "bytes")


if __name__ == "__main__":
    main()
