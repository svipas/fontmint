"""Regenerate assets/logo.svg. The lettering is converted to paths, so the SVG
needs no fonts. It is set in Inter Clear (Inter with ss02, built by fontmint).

Usage:
    .venv/bin/python assets/make_logo.py dist/InterClear/ttf-unhinted/InterClear-Bold.ttf \
        dist/InterClear/ttf-unhinted/InterClear-SemiBold.ttf assets/logo.svg
"""

from __future__ import annotations

import sys

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

font_bold, font_semi, out = sys.argv[1], sys.argv[2], sys.argv[3]


def text_path(fontfile, text, size, x, baseline, tracking=0.0, center=None):
    """Return (SVG path data, width) for `text` at `size` px. With `center`, the
    text's bounding box is centered on that point instead of using x/baseline."""
    font = TTFont(fontfile)
    glyphs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    scale = size / upm
    names = [cmap[ord(c)] for c in text]
    width = sum(glyphs[n].width for n in names) * scale + tracking * size * (len(names) - 1)
    if center is not None:
        bounds = BoundsPen(glyphs)
        advance = 0
        for n in names:
            glyphs[n].draw(TransformPen(bounds, (1, 0, 0, 1, advance, 0)))
            advance += glyphs[n].width + tracking * upm
        xmin, ymin, xmax, ymax = bounds.bounds
        x = center[0] - ((xmin + xmax) / 2) * scale
        baseline = center[1] + ((ymin + ymax) / 2) * scale
    pen = SVGPathPen(glyphs, lambda v: f"{v:.2f}".rstrip("0").rstrip("."))
    for n in names:
        glyphs[n].draw(TransformPen(pen, (scale, 0, 0, -scale, x, baseline)))
        x += glyphs[n].width * scale + tracking * size
    return pen.getCommands(), width


W, H = 560, 160
cx, cy, r = 80, 80, 64
aa, _ = text_path(font_bold, "Aa", 54, 0, 0, tracking=-0.02, center=(cx, cy + 1))
font_d, font_w = text_path(font_semi, "font", 76, 172, 108, tracking=-0.025)
mint_d, _ = text_path(font_bold, "mint", 76, 172 + font_w + 76 * -0.025, 108, tracking=-0.025)

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="fontmint">
  <title>fontmint</title>
  <defs>
    <linearGradient id="coin" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#6EF2C8"/>
      <stop offset="0.55" stop-color="#1FC795"/>
      <stop offset="1" stop-color="#0B8F6A"/>
    </linearGradient>
    <linearGradient id="face" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#2FD3A2"/>
      <stop offset="1" stop-color="#0E9E75"/>
    </linearGradient>
    <linearGradient id="shine" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity="0.32"/>
      <stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="word" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#1FC795"/>
      <stop offset="1" stop-color="#0FA37F"/>
    </linearGradient>
  </defs>
  <!-- coin -->
  <circle cx="{cx}" cy="{cy + 3}" r="{r}" fill="#0A7556" opacity="0.35"/>
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#coin)"/>
  <circle cx="{cx}" cy="{cy}" r="{r - 2.5}" fill="none" stroke="#0B8F6A" stroke-width="3.5" stroke-dasharray="2.2 3.2" opacity="0.55"/>
  <circle cx="{cx}" cy="{cy}" r="{r - 9}" fill="url(#face)"/>
  <circle cx="{cx}" cy="{cy}" r="{r - 9}" fill="none" stroke="#FFFFFF" stroke-opacity="0.35" stroke-width="1.5"/>
  <ellipse cx="{cx}" cy="{cy - r * 0.38:.1f}" rx="{(r - 9) * 0.82:.1f}" ry="{r * 0.36:.1f}" fill="url(#shine)"/>
  <path d="{aa}" fill="#0A7556" opacity="0.35" transform="translate(0 2)"/>
  <path d="{aa}" fill="#FFFFFF"/>
  <!-- wordmark -->
  <path d="{font_d}" fill="#7D8590"/>
  <path d="{mint_d}" fill="url(#word)"/>
</svg>
'''
with open(out, "w", encoding="utf-8") as f:
    f.write(svg)
print("wrote", out, len(svg), "bytes")
