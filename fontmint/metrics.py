"""Line height and letter spacing.

Both are given like their CSS counterparts, as multiples of the font size: a line
height of 1.4 spaces lines 1.4 em apart, a letter spacing of 0.05 adds 0.05 em after
each character.
"""

from __future__ import annotations

import math

from fontTools.ttLib import TTFont

LINE_HEIGHT_RANGE = (0.5, 3.0)
LETTER_SPACING_RANGE = (-0.5, 1.0)

# MVAR tags that vary the line metrics fontmint sets; fixed values must not get deltas.
LINE_METRIC_TAGS = {"hasc", "hdsc", "hlgp", "hcla", "hcld"}
USE_TYPO_METRICS = 1 << 7  # OS/2 fsSelection bit, defined from OS/2 version 4


def line_height(font: TTFont) -> float:
    """The font's current line spacing, as a multiple of the font size."""
    hhea = font["hhea"]
    return (hhea.ascent - hhea.descent + hhea.lineGap) / font["head"].unitsPerEm


def set_line_height(font: TTFont, value: float) -> None:
    """Space lines `value` em apart. The extra (or missing) space is split equally
    above and below the text, as CSS does, and written to every set of line metrics
    apps read, with no line gap: hhea (macOS) and OS/2 typo (Windows, browsers; the
    font is marked to use them). The Windows clipping area (usWin*) only ever grows,
    so no glyph gets cut off."""
    hhea, os2 = font["hhea"], font["OS/2"]
    extra = round(value * font["head"].unitsPerEm) - (hhea.ascent - hhea.descent)
    ascent = hhea.ascent + math.ceil(extra / 2)
    descent = hhea.descent - math.floor(extra / 2)
    hhea.ascent, hhea.descent, hhea.lineGap = ascent, descent, 0
    os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap = ascent, descent, 0
    os2.usWinAscent = max(os2.usWinAscent, ascent)
    os2.usWinDescent = max(os2.usWinDescent, -descent)
    if os2.version >= 2:  # versions 2-4 have the same fields; 4 defines the bit
        os2.version = max(os2.version, 4)
        os2.fsSelection |= USE_TYPO_METRICS
    if "MVAR" in font:
        mvar = font["MVAR"].table
        mvar.ValueRecord = [r for r in mvar.ValueRecord if r.ValueTag not in LINE_METRIC_TAGS]
        mvar.ValueRecordCount = len(mvar.ValueRecord)
        if not mvar.ValueRecord:
            del font["MVAR"]


def add_letter_spacing(font: TTFont, value: float) -> None:
    """Add `value` em after every glyph that has a width, as CSS letter-spacing does.
    Zero-width glyphs (accents placed on other letters) keep their width, and outlines
    don't move, so kerning and accent positions stay correct."""
    delta = round(value * font["head"].unitsPerEm)
    hmtx = font["hmtx"]
    for name, (advance, lsb) in hmtx.metrics.items():
        if advance > 0:
            hmtx.metrics[name] = (max(advance + delta, 0), lsb)
    advances = [advance for advance, _ in hmtx.metrics.values()]
    font["hhea"].advanceWidthMax = max(advances)
    os2 = font["OS/2"]
    if os2.version < 3:  # an average weighted by letter frequency, roughly shifted by the same amount
        os2.xAvgCharWidth += delta
    elif widths := [a for a in advances if a > 0]:
        os2.xAvgCharWidth = round(sum(widths) / len(widths))
    if "hdmx" in font:  # stored widths per pixel size, now wrong; renderers compute them without it
        del font["hdmx"]
    if "CFF " in font:
        _sync_cff_widths(font)


def _sync_cff_widths(font: TTFont) -> None:
    """CFF outlines store each glyph's width a second time; keep it equal to hmtx."""
    from fontTools.misc.psCharStrings import T2WidthExtractor

    top = font["CFF "].cff.topDictIndex[0]
    hmtx = font["hmtx"]
    for name in top.CharStrings.keys():
        charstring = top.CharStrings[name]
        private = charstring.private  # CID-keyed fonts have one per font dict
        extractor = T2WidthExtractor(getattr(private, "Subrs", []), top.GlobalSubrs, private.nominalWidthX,
                                     private.defaultWidthX)
        charstring.decompile()
        extractor.execute(charstring)
        width = hmtx[name][0]
        if width == extractor.width:
            continue
        operand = width - private.nominalWidthX
        if extractor.gotWidth:
            charstring.program[0] = operand
        else:  # the width was the default, so it isn't written yet
            charstring.program.insert(0, operand)
