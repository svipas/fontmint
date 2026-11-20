"""Hinting and format conversion for static fonts built from variable fonts.
Native helpers (ttfautohint, skia-pathops, cffsubr) are imported only when used."""

from __future__ import annotations

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

from .common import FontmintError, get_name

TRUETYPE_HINTING_TABLES = ("fpgm", "prep", "cvt ", "cvar", "hdmx", "LTSH", "VDMX", "gasp")


def has_hinting(font: TTFont) -> bool:
    """True if the font ships real TrueType hinting. A lone short `prep` (scan
    control, added by font build tools to unhinted fonts) doesn't count."""
    if "fpgm" in font or "cvt " in font:
        return True
    glyf = font.get("glyf")
    return bool(glyf) and any(
        getattr(glyf[name], "program", None) and glyf[name].program.getBytecode() for name in font.getGlyphOrder()
    )


def strip_hinting(font: TTFont) -> TTFont:
    """Remove hinting tables and glyph instructions from a TrueType font, in place."""
    for tag in TRUETYPE_HINTING_TABLES:
        if tag in font:
            del font[tag]
    if "glyf" in font:
        glyf = font["glyf"]
        for name in font.getGlyphOrder():
            glyf[name].removeHinting()
        maxp = font["maxp"]
        maxp.maxZones = 1
        for field in (
            "maxTwilightPoints",
            "maxStorage",
            "maxFunctionDefs",
            "maxInstructionDefs",
            "maxStackElements",
            "maxSizeOfInstructions",
        ):
            setattr(maxp, field, 0)
    return font


def autohint(font_bytes: bytes) -> bytes:
    """Hinted version of a static TrueType font, made with ttfautohint."""
    from ttfautohint import ttfautohint

    try:
        return ttfautohint(in_buffer=font_bytes)
    except Exception as e:  # ttfautohint fails on fonts without Latin reference glyphs, e.g. icon fonts
        reason = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
        raise FontmintError(f"ttfautohint can't hint this font ({reason}); build it with --no-hint") from e


def ttf_to_otf(font: TTFont, remove_overlaps: bool = True, subroutinize: bool = True) -> TTFont:
    """Convert a static TrueType-outline font to CFF (OTF).

    - Overlapping contours are merged first (skia-pathops): CFF has no overlap
      flag, so merged outlines render cleanly everywhere. Same filled area.
    - Runs of quadratic curves are merged into as few cubic curves as possible
      (Qu2Cu, max error 1 font unit); contours that can't be merged fall back to
      exact quadratic→cubic conversion.
    - CFF charstrings are subroutinized with cffsubr (roughly halves the size).
    - TrueType hinting is dropped and no CFF hints are added.

    Converts `font` in place and returns it.
    """
    if "glyf" not in font:
        return font
    if remove_overlaps:
        from fontTools.ttLib.removeOverlaps import removeOverlaps

        removeOverlaps(font)
    glyph_set = font.getGlyphSet()
    hmtx = font["hmtx"]
    max_err = 1.0  # font units; fontTools' default. Tighter gained nothing measurable.
    charstrings = {}
    for gname in font.getGlyphOrder():
        rec = DecomposingRecordingPen(glyph_set)
        glyph_set[gname].draw(rec)
        pen = T2CharStringPen(hmtx[gname][0], glyph_set)
        try:
            rec.replay(Qu2CuPen(pen, max_err=max_err, all_cubic=True))
        except NotImplementedError:  # contour without on-curve points
            pen = T2CharStringPen(hmtx[gname][0], glyph_set)
            rec.replay(pen)
        charstrings[gname] = pen.getCharString()

    post = font["post"]
    ps_name = get_name(font, 6) or "Font"
    font_info = {
        "FullName": get_name(font, 4) or ps_name,
        "FamilyName": get_name(font, 16) or get_name(font, 1) or ps_name,
        "Weight": get_name(font, 17) or get_name(font, 2) or "Regular",
        "ItalicAngle": post.italicAngle,
        "UnderlinePosition": post.underlinePosition,
        "UnderlineThickness": post.underlineThickness,
        "isFixedPitch": post.isFixedPitch,
    }
    fb = FontBuilder(font=font)
    fb.isTTF = False
    for tag in ("glyf", "loca", "gvar", "cvt ", "fpgm", "prep", "cvar", "hdmx", "LTSH", "VDMX", "DSIG"):
        if tag in font:
            del font[tag]
    fb.setupCFF(ps_name, font_info, charstrings, {})
    font["maxp"].tableVersion = 0x00005000
    post.formatType = 3.0
    font.sfntVersion = "OTTO"

    # Outlines changed (merged overlaps, new curves): left side bearings must match the CFF xMin.
    cff_glyphs = font.getGlyphSet()
    for gname in font.getGlyphOrder():
        bounds = BoundsPen(cff_glyphs)
        cff_glyphs[gname].draw(bounds)
        hmtx[gname] = (hmtx[gname][0], round(bounds.bounds[0]) if bounds.bounds else 0)

    if subroutinize:
        import cffsubr

        cffsubr.subroutinize(font)
    return font
