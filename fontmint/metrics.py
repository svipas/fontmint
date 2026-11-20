"""Line height and letter spacing.

Both are given like their CSS counterparts, as multiples of the font size: a line
height of 1.4 spaces lines 1.4 em apart, a letter spacing of 0.05 adds 0.05 em after
each character.
"""

from __future__ import annotations

import math
from collections import Counter

from fontTools.misc.psCharStrings import T2WidthExtractor
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
    above and below the text, as CSS does, and written with no line gap to hhea
    (macOS) and the OS/2 typo values (browsers and most Windows apps; the font is
    marked to use them). The Windows clipping area (usWin*) only ever grows, so no
    glyph gets cut off - old Windows apps that take their line height from it
    don't get a smaller one."""
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
    if "VDMX" in font:  # stored line metrics per pixel size, now wrong; renderers compute them without it
        del font["VDMX"]
    if "MVAR" in font:
        mvar = font["MVAR"].table
        mvar.ValueRecord = [r for r in mvar.ValueRecord if r.ValueTag not in LINE_METRIC_TAGS]
        mvar.ValueRecordCount = len(mvar.ValueRecord)
        if not mvar.ValueRecord:
            del font["MVAR"]


def fixed_width(font: TTFont) -> int:
    """The character width of a monospaced font, 0 for a proportional one. Monospaced
    means every character has the same width - zero-width marks and double-width
    glyphs (e.g. an ffi ligature, or CJK next to Latin) aside."""
    hmtx = font["hmtx"]
    widths = Counter(hmtx[glyph][0] for glyph in set((font.getBestCmap() or {}).values()))
    common = max(widths, key=widths.__getitem__, default=0)
    return common if set(widths) <= {0, common, 2 * common} else 0


def add_letter_spacing(font: TTFont, value: float) -> None:
    """Add `value` em after every glyph that has a width, as CSS letter-spacing does.
    Zero-width glyphs (accents placed on other letters) keep their width, and outlines
    don't move, so kerning and accent positions stay correct. In a monospaced font,
    double-width glyphs get twice the space, so they still fill two cells."""
    delta = round(value * font["head"].unitsPerEm)
    if not delta:
        return
    double = 2 * fixed_width(font)
    hmtx = font["hmtx"]
    for name, (advance, lsb) in hmtx.metrics.items():
        if advance > 0:
            hmtx.metrics[name] = (max(advance + (2 * delta if advance == double else delta), 0), lsb)
    advances = [advance for advance, _ in hmtx.metrics.values()]
    font["hhea"].advanceWidthMax = max(advances)
    os2 = font["OS/2"]
    if os2.version < 3:  # an average weighted by letter frequency, roughly shifted by the same amount
        os2.xAvgCharWidth += delta
    elif widths := [a for a in advances if a > 0]:
        os2.xAvgCharWidth = round(sum(widths) / len(widths))
    for tag in ("hdmx", "LTSH"):  # widths stored per pixel size, now wrong; renderers compute them without these
        if tag in font:
            del font[tag]
    if "CFF " in font:
        _sync_cff_widths(font)


class _WidthReader(T2WidthExtractor):
    """Reads a charstring's width, and whether the charstring states it (`explicit`)
    or leaves it to the font's default width."""

    explicit = False

    def popallWidth(self, evenOdd=0):
        if not self.gotWidth:
            self.explicit = bool(evenOdd ^ (len(self.operandStack) % 2))
        return super().popallWidth(evenOdd)


def _sync_cff_widths(font: TTFont) -> None:
    """CFF outlines store each glyph's width a second time; keep it equal to hmtx.
    A stated width is the first number of a charstring; one that isn't stated (the
    glyph has the font's default width) is added in front."""
    cff = font["CFF "].cff
    top = cff.topDictIndex[0]
    hmtx = font["hmtx"]

    def stale():
        for name in top.CharStrings.keys():
            charstring = top.CharStrings[name]
            private = charstring.private  # CID-keyed fonts have one per font dict
            reader = _WidthReader(
                getattr(private, "Subrs", []), top.GlobalSubrs, private.nominalWidthX, private.defaultWidthX
            )
            reader.execute(charstring)
            if reader.width != hmtx[name][0]:
                yield charstring, reader.explicit, hmtx[name][0] - private.nominalWidthX

    def in_subroutine(charstring, explicit) -> bool:
        """The stated width isn't in the charstring itself: its first number is the
        index of the subroutine that holds it."""
        return explicit and len(charstring.program) > 1 and charstring.program[1] in ("callsubr", "callgsubr")

    if any(in_subroutine(charstring, explicit) for charstring, explicit, _ in stale()):
        cff.desubroutinize()
    for charstring, explicit, operand in list(stale()):
        if explicit:
            charstring.program[0] = operand
        else:
            charstring.program.insert(0, operand)
