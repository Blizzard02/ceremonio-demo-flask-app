"""One-shot generator for Ceremonio PWA icons. Dev-only. Run: python tools/generate_icons.py

Draws the brand tile: a soft-pink rounded square with a "C" shaped like a
cherry-blossom branch (plum-brown arc) crowned with pink/white blossoms,
golden centers, buds and leaves. Matches the in-app inline SVG logo.

Rendered at 4x supersampling then downscaled for clean anti-aliasing.
"""
import os
import math
from PIL import Image, ImageDraw

OUT = os.path.join(os.path.dirname(__file__), "..", "static", "icons")
os.makedirs(OUT, exist_ok=True)

SS = 4  # supersampling factor

TILE_TOP = (253, 238, 246)   # #fdeef6
TILE_BOT = (247, 203, 225)   # #f7cbe1
BRANCH = (131, 79, 99)       # #834f63
PETAL = (255, 255, 255)
PETAL_SOFT = (251, 213, 230)
CENTER = (247, 185, 212)     # #f7b9d4
GOLD = (244, 183, 63)        # #f4b73f
LEAF = (167, 201, 164)       # #a7c9a4
BUD_A = (249, 198, 220)
BUD_B = (251, 213, 230)


def _lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def blossom(draw, cx, cy, scale):
    """5 white petals + soft accent + golden center, on a 64-unit design grid (already scaled)."""
    petal_len = 7.4 * scale
    petal_w = 4.2 * scale
    for k in range(5):
        ang = math.radians(k * 72 - 90)
        px = cx + math.cos(ang) * petal_len * 0.6
        py = cy + math.sin(ang) * petal_len * 0.6
        bbox = [px - petal_w / 2, py - petal_len / 2, px + petal_w / 2, py + petal_len / 2]
        # rotate by drawing an ellipse on a temp layer
        layer = Image.new("RGBA", draw._image.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ld.ellipse(bbox, fill=PETAL + (255,))
        layer = layer.rotate(math.degrees(ang) + 90, center=(px, py), resample=Image.BICUBIC)
        draw._image.alpha_composite(layer)
    draw.ellipse([cx - 2.0 * scale, cy - 2.0 * scale, cx + 2.0 * scale, cy + 2.0 * scale], fill=CENTER + (255,))
    draw.ellipse([cx - 0.95 * scale, cy - 0.95 * scale, cx + 0.95 * scale, cy + 0.95 * scale], fill=GOLD + (255,))


def make_icon(size, path, maskable=False):
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # soft-pink vertical gradient tile
    grad = Image.new("RGB", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        gd.line([(0, y), (s, y)], fill=_lerp(TILE_TOP, TILE_BOT, y / s))
    radius = 0 if maskable else int(s * 0.25)
    if maskable:
        img.paste(grad, (0, 0))
    else:
        img.paste(grad, (0, 0), rounded_mask(s, radius))

    draw = ImageDraw.Draw(img)
    draw._image = img  # for blossom alpha_composite helper

    # design happens on a 64-grid; map to pixels. Maskable: shrink to safe ~80% center.
    inset = 0.10 if maskable else 0.0
    def U(v):  # unit (0..64) -> px
        return (inset + (v / 64.0) * (1 - 2 * inset)) * s

    # "C" branch arc, open to the right. Center (32,32), radius 18 in design units.
    cx, cy = U(32), U(32)
    rad = (18 / 64.0) * (1 - 2 * inset) * s
    stroke = max(2, int((5.2 / 64.0) * (1 - 2 * inset) * s))
    bbox = [cx - rad, cy - rad, cx + rad, cy + rad]
    # arc opening on the right: gap between -43 and 43 degrees
    draw.arc(bbox, start=43, end=317, fill=BRANCH, width=stroke)
    # round the arc tips
    for a in (43, 317):
        ax = cx + rad * math.cos(math.radians(a))
        ay = cy + rad * math.sin(math.radians(a))
        r = stroke / 2
        draw.ellipse([ax - r, ay - r, ax + r, ay + r], fill=BRANCH)

    sc = (1 / 64.0) * (1 - 2 * inset) * s  # design-unit scale for blossoms

    # leaves
    for (lx, ly, rot) in ((12.5, 29.5, -38), (20, 44, 28)):
        layer = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        ex, ey = U(lx), U(ly)
        ld.ellipse([ex - 3.0 * sc, ey - 1.6 * sc, ex + 3.0 * sc, ey + 1.6 * sc], fill=LEAF + (255,))
        layer = layer.rotate(rot, center=(ex, ey), resample=Image.BICUBIC)
        img.alpha_composite(layer)

    # buds
    draw.ellipse([U(22.5) - 1.9 * sc, U(13.8) - 1.9 * sc, U(22.5) + 1.9 * sc, U(13.8) + 1.9 * sc], fill=BUD_A)
    draw.ellipse([U(40.5) - 1.6 * sc, U(15.2) - 1.6 * sc, U(40.5) + 1.6 * sc, U(15.2) + 1.6 * sc], fill=BUD_B)

    # blossoms
    blossom(draw, U(31), U(16), 1.2 * sc)
    blossom(draw, U(15.5), U(28), 0.92 * sc)
    blossom(draw, U(44.5), U(45), 0.86 * sc)

    out = img.resize((size, size), Image.LANCZOS)
    out.save(path)
    print("wrote", os.path.abspath(path))


make_icon(192, os.path.join(OUT, "icon-192.png"))
make_icon(512, os.path.join(OUT, "icon-512.png"))
make_icon(512, os.path.join(OUT, "icon-maskable-512.png"), maskable=True)
make_icon(180, os.path.join(OUT, "apple-touch-icon.png"))
