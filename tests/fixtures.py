"""Tiny test fonts, built in code — no binary fixtures in the repo.

Every font is a family called "Test Sans" with a handful of rectangle glyphs:

    zero  → zero.ss01   (ss01 swaps it, so freezing ss01 remaps U+0030)
    I     → I.ss01
    I zero → H          (liga: a ligature, which can't be frozen)
    H O o x n space .notdef   (enough for ttfautohint's Latin analysis)

The copyright and trademark notices deliberately contain the family name, so the
tests can check that renaming leaves them alone.
"""

from __future__ import annotations

import io
from functools import cache

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables import ttProgram
from fontTools.ttLib.tables.TupleVariation import TupleVariation

FAMILY = "Test Sans"
COPYRIGHT = "Copyright 2026 The Test Sans Project Authors"
TRADEMARK = "Test Sans is a trademark of Nobody"
ADVANCE = 600
ITALIC_ANGLE = -10

# glyph → (x0, y0, x1, y1) of its rectangle; None for an empty glyph
LATIN = {
    ".notdef": (50, 0, 450, 700), "space": None,
    "zero": (60, 0, 440, 700), "zero.ss01": (60, -20, 440, 720),
    "I": (200, 0, 300, 700), "I.ss01": (150, 0, 350, 700),
    "H": (60, 0, 540, 700), "O": (50, -10, 550, 710), "o": (50, -10, 450, 510),
    "x": (30, 0, 470, 500), "n": (60, 0, 440, 500),
}
LATIN_CMAP = {0x20: "space", 0x30: "zero", 0x49: "I", 0x48: "H", 0x4F: "O", 0x6F: "o", 0x78: "x", 0x6E: "n"}
LATIN_FEATURES = """
feature ss01 { sub zero by zero.ss01; sub I by I.ss01; } ss01;
feature liga { sub I zero by H; } liga;
"""
# A font ttfautohint can't hint: no Latin reference glyphs at all.
SYMBOLS = {".notdef": (50, 0, 450, 700), "arrowleft": (50, 200, 550, 400), "arrowright": (50, 250, 550, 450)}
SYMBOLS_CMAP = {0x2190: "arrowleft", 0x2192: "arrowright"}

INSTANCES = [  # (style name, wght, wdth)
    ("Regular", 400, 100), ("Bold", 700, 100),
    ("Condensed", 400, 75), ("Condensed Bold", 700, 75),
]
# Dummy TrueType hinting: must survive static passthrough byte for byte, and be
# stripped from the "-unhinted" outputs of a hinted variable font.
HINTING_TABLES = {"fpgm": b"\xb0\x00", "prep": b"\xb0\x01", "cvt ": b"\x00\x10\x00\x20"}
GLYPH_PROGRAM = b"\xb0\x00"  # PUSHB[0] 0
SCAN_CONTROL_PREP = b"\xb8\x01\xff\x85\xb0\x04\x8d"  # the 7-byte prep in JetBrains Mono / Recursive


def _draw_rect(pen, box) -> None:
    if box:
        x0, y0, x1, y1 = box
        pen.moveTo((x0, y0))
        pen.lineTo((x0, y1))
        pen.lineTo((x1, y1))
        pen.lineTo((x1, y0))
        pen.closePath()


def _builder(is_ttf: bool, boxes: dict, cmap: dict, features: str, italic: bool, hinted: bool,
             scan_control: bool = False) -> FontBuilder:
    style = "Italic" if italic else "Regular"
    fb = FontBuilder(1000, isTTF=is_ttf)
    fb.setupGlyphOrder(list(boxes))
    fb.setupCharacterMap(cmap)
    metrics = {name: (ADVANCE, box[0] if box else 0) for name, box in boxes.items()}
    if is_ttf:
        glyphs = {}
        for name, box in boxes.items():
            pen = TTGlyphPen(None)
            _draw_rect(pen, box)
            glyphs[name] = pen.glyph()
            if hinted and box:
                glyphs[name].program = ttProgram.Program()
                glyphs[name].program.fromBytecode(GLYPH_PROGRAM)
        fb.setupGlyf(glyphs)
    else:
        charstrings = {}
        for name, box in boxes.items():
            pen = T2CharStringPen(ADVANCE, None)
            _draw_rect(pen, box)
            charstrings[name] = pen.getCharString()
        fb.setupCFF(f"TestSans-{style}", {"FullName": f"{FAMILY} {style}", "FamilyName": FAMILY}, charstrings, {})
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({
        "copyright": COPYRIGHT,
        "familyName": FAMILY,
        "styleName": style,
        "uniqueFontIdentifier": f"1.000;TEST;TestSans-{style}",
        "fullName": f"{FAMILY} {style}",
        "version": "Version 1.000",
        "psName": f"TestSans-{style}",
        "trademark": TRADEMARK,
        "licenseDescription": "Test Sans is licensed for testing only.",
    })
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    if features:
        fb.addOpenTypeFeatures(features)
    if italic:
        fb.font["post"].italicAngle = ITALIC_ANGLE
        fb.font["OS/2"].fsSelection = (fb.font["OS/2"].fsSelection | 1) & ~(1 << 6)
        fb.font["head"].macStyle |= 2
    if hinted:
        for tag, data in HINTING_TABLES.items():
            table = newTable(tag)
            table.decompile(data, fb.font)
            fb.font[tag] = table
    if scan_control:  # what font build tools add to *unhinted* fonts: a tiny prep + gasp
        fb.font["prep"] = newTable("prep")
        fb.font["prep"].decompile(SCAN_CONTROL_PREP, fb.font)
        fb.font["gasp"] = newTable("gasp")
        fb.font["gasp"].version = 1
        fb.font["gasp"].gaspRange = {0xFFFF: 0x000F}
    return fb


def _add_variations(fb: FontBuilder, boxes: dict, italic: bool) -> None:
    """wght 100–900 (default 400): bolder = wider; wdth 75–100: condensed = narrower."""
    fb.setupFvar(
        axes=[("wght", 100, 400, 900, "Weight"), ("wdth", 75, 100, 100, "Width")],
        instances=[
            {"location": {"wght": w, "wdth": d}, "stylename": _italic_name(s) if italic else s}
            for s, w, d in INSTANCES
        ],
    )

    def deltas(dx):  # 4 rectangle points + 4 phantom points; move the right edge and advance
        return [(0, 0), (0, 0), (dx, 0), (dx, 0), (0, 0), (dx, 0), (0, 0), (0, 0)]

    fb.setupGvar({
        name: [
            TupleVariation({"wght": (0, 1, 1)}, deltas(80)),
            TupleVariation({"wght": (-1, -1, 0)}, deltas(-40)),
            TupleVariation({"wdth": (-1, -1, 0)}, deltas(-100)),
        ]
        for name, box in boxes.items() if box
    })


def _italic_name(style: str) -> str:
    return "Italic" if style == "Regular" else f"{style} Italic"


def _save(font: TTFont, flavor: str | None = None) -> bytes:
    font.flavor = flavor
    buf = io.BytesIO()
    font.save(buf)
    return buf.getvalue()


@cache
def static_ttf(hinted: bool = True) -> bytes:
    """Static TrueType font; hinted=True adds dummy hinting tables and glyph programs."""
    return _save(_builder(True, LATIN, LATIN_CMAP, LATIN_FEATURES, italic=False, hinted=hinted).font)


@cache
def static_otf() -> bytes:
    """Static CFF (OTF) font."""
    return _save(_builder(False, LATIN, LATIN_CMAP, LATIN_FEATURES, italic=False, hinted=False).font)


@cache
def static_woff2() -> bytes:
    return _save(TTFont(io.BytesIO(static_ttf(hinted=False))), "woff2")


@cache
def variable_ttf(italic: bool = False, hinted: bool = False, scan_control: bool = False) -> bytes:
    """Variable TrueType font: wght 100–900 (default 400), wdth 75–100 (default 100),
    four named instances. hinted=True gives it its own (dummy) TrueType hinting;
    scan_control=True only adds the prep/gasp that build tools put in unhinted fonts."""
    fb = _builder(True, LATIN, LATIN_CMAP, LATIN_FEATURES, italic=italic, hinted=hinted, scan_control=scan_control)
    _add_variations(fb, LATIN, italic)
    return _save(fb.font)


@cache
def symbol_variable_ttf() -> bytes:
    """Variable font with only arrow glyphs — ttfautohint refuses to hint it."""
    fb = _builder(True, SYMBOLS, SYMBOLS_CMAP, "", italic=False, hinted=False)
    _add_variations(fb, SYMBOLS, italic=False)
    return _save(fb.font)


def open_font(data: bytes) -> TTFont:
    return TTFont(io.BytesIO(data))
