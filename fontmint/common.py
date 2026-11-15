"""Shared helpers: errors, loading/saving fonts, reading names."""

from __future__ import annotations

import io

from fontTools.ttLib import TTFont

FORMATS = ("ttf", "otf", "woff2")


class FontmintError(Exception):
    """Invalid input or options (bad font, missing feature, value out of range, …)."""


REQUIRED_TABLES = ("head", "name", "cmap", "maxp", "hmtx", "post", "OS/2")


def load(font_bytes: bytes, recalc: bool = True, check: bool = True) -> TTFont:
    """Open a font from bytes. recalc=False keeps bounding boxes and timestamps
    exactly as stored (used when a font should pass through unchanged).
    check=True decompiles every table once up front, so a damaged file fails here
    with a clear error instead of somewhere later (fontTools reads tables lazily)."""
    if font_bytes[:4] == b"ttcf":
        raise FontmintError("font collections (.ttc) aren't supported; extract the fonts first")
    try:
        if check:
            # Checked on a throwaway copy: a decompiled table gets re-serialized on
            # save, and pass-through fonts should only change where fontmint edits them.
            probe = TTFont(io.BytesIO(font_bytes))
            if missing := [t for t in REQUIRED_TABLES if t not in probe]:
                raise FontmintError(f"missing required table(s): {', '.join(missing)}")
            probe.ensureDecompiled()
        return TTFont(io.BytesIO(font_bytes), recalcBBoxes=recalc, recalcTimestamp=recalc)
    except FontmintError as e:
        raise FontmintError(f"not a usable font: {e}") from e
    except Exception as e:
        raise FontmintError(f"not a readable font ({type(e).__name__}: {e})") from e


def to_bytes(font: TTFont, flavor: str | None = None) -> bytes:
    """Serialize `font` as plain TTF/OTF (flavor=None), "woff" or "woff2"."""
    previous, font.flavor = font.flavor, flavor
    try:
        buf = io.BytesIO()
        font.save(buf)
        return buf.getvalue()
    finally:
        font.flavor = previous


def extension(font: TTFont) -> str:
    """File extension matching the font's container and outlines."""
    if font.flavor in ("woff", "woff2"):
        return font.flavor
    return "otf" if font.sfntVersion == "OTTO" else "ttf"


def text(record) -> str:
    """A name record's text. Bytes that can't be decoded (seen in old Mac records)
    become U+FFFD instead of an error."""
    return record.toUnicode(errors="replace")


def get_name(font: TTFont, name_id: int) -> str | None:
    """A name's text: the Windows English record, else whichever the font has."""
    name = font["name"]
    rec = name.getName(name_id, 3, 1, 0x409) or name.getName(name_id, 3, 1)
    if not rec:
        rec = next((r for r in name.names if r.nameID == name_id), None)
    return text(rec) if rec else None


def family_name(font: TTFont) -> str:
    """The family name, preferring English records over localized ones."""
    name = font["name"]
    for name_id in (16, 1):
        rec = name.getName(name_id, 3, 1, 0x409) or name.getName(name_id, 1, 0, 0)
        family = text(rec) if rec else ""
        if family and name_id == 1:
            family = _without_style(family, get_name(font, 6) or "")
        if family:
            return family
    return get_name(font, 16) or get_name(font, 1) or "Font"


def _without_style(family: str, ps_name: str) -> str:
    """Older fonts have no name ID 16 and keep part of the style in ID 1 ("Acme Sans
    SemiBold"). The PostScript name ("AcmeSans-SemiBold") shows where the family ends."""
    prefix, dash, _ = ps_name.partition("-")
    if dash and prefix and family.replace(" ", "").startswith(prefix):
        for end in range(1, len(family)):
            if family[:end].replace(" ", "") == prefix and family[end] == " ":
                return family[:end]
    return family


def is_italic(font: TTFont) -> bool:
    return (
        font["post"].italicAngle != 0
        or bool(font["OS/2"].fsSelection & 1)
        or bool(font["head"].macStyle & 2)
    )


def is_variable(font: TTFont) -> bool:
    return "fvar" in font
