"""Family renaming, style names and OS/2 weight/width classes."""

from __future__ import annotations

from fontTools.ttLib import TTFont

from .common import FontmintError, get_name

WEIGHT_NAMES = {
    100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium",
    600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black",
}
# (wdth axis value in %, style name); index + 1 = OS/2 usWidthClass
WIDTHS = [
    (50, "UltraCondensed"), (62.5, "ExtraCondensed"), (75, "Condensed"), (87.5, "SemiCondensed"),
    (100, ""), (112.5, "SemiExpanded"), (125, "Expanded"), (150, "ExtraExpanded"), (200, "UltraExpanded"),
]
# Name IDs that carry the family name. Copyright (0), trademark (7), manufacturer,
# designer, description, URLs and license (8–14) are never touched.
FAMILY_NAME_IDS = {1, 3, 4, 6, 16, 18, 20, 21, 25}
POSTSCRIPT_NAME_IDS = {6, 20, 25}
# Localized versions of these would keep identifying the original family.
LOCALIZED_FAMILY_IDS = {1, 4, 16, 18, 21}
WINDOWS_FAMILY_LIMIT = 31  # characters in name ID 1 that Windows apps reliably show
# Characters PostScript names may not contain (besides spaces, which are dropped),
# plus the ones Windows forbids in file and folder names.
FORBIDDEN_CHARS = set("[](){}<>/%") | set('\\:*?"|')
LINKED_WORDS = ("Regular", "Bold", "Italic", "Oblique")  # the style-linking part of a style


def check_name(value: str, what: str) -> None:
    """Reject names that would give an invalid PostScript name or an unsafe folder name."""
    bad = sorted({c for c in value if c != " " and (not 33 <= ord(c) <= 126 or c in FORBIDDEN_CHARS)})
    if bad:
        raise FontmintError(f"{what} may only use ASCII letters, digits, spaces and punctuation "
                            f"except {''.join(sorted(FORBIDDEN_CHARS))} (found {' '.join(bad)})")
    if value.replace(" ", "").strip(".") == "":
        raise FontmintError(f"{what} must contain letters or digits")


def check_ps_length(name: str) -> str:
    if len(name) > 63:
        raise FontmintError(f"PostScript name '{name}' is longer than 63 characters; use a shorter --name")
    return name


def ps_name(family: str, style: str) -> str:
    """PostScript name (also the static file name), at most 63 characters."""
    return check_ps_length(f"{safe_path_part(family)}-{safe_path_part(style)}")


def safe_path_part(text: str) -> str:
    """A folder or file name made from text read out of a font, which can't be
    trusted: unsafe characters become "_", so it can never leave the output folder."""
    cleaned = "".join(c if 33 <= ord(c) <= 126 and c not in FORBIDDEN_CHARS else "_" for c in text.replace(" ", ""))
    return cleaned.strip(".") or "font"


def rename_family(font: TTFont, old: str, new: str) -> list[str]:
    """Replace the family name in the name records that identify the font (and in
    instance / PostScript names ≥ 256), plus the CFF names of OTF fonts.
    Returns warnings about original names that couldn't be replaced."""
    old_ps, new_ps = old.replace(" ", ""), new.replace(" ", "")
    old_ps_name = get_name(font, 6)
    name = font["name"]
    name.names = [r for r in name.names if r.nameID not in LOCALIZED_FAMILY_IDS or _is_english(r)]
    for rec in name.names:
        if rec.nameID not in FAMILY_NAME_IDS and rec.nameID < 256:
            continue
        s = rec.toUnicode()
        # PostScript-style names get the space-less family ("Inter-Medium" →
        # "FooNew-Medium"); display names get the real one ("Inter" → "Foo New").
        # Unique IDs (3) and instance names (≥ 256) can be either kind.
        if rec.nameID in POSTSCRIPT_NAME_IDS or ((rec.nameID == 3 or rec.nameID >= 256) and " " not in s):
            s2 = s.replace(old_ps, new_ps)
        else:
            s2 = s.replace(old, new)
        if s2 != s:
            rec.string = s2

    # A PostScript name that doesn't contain the family ("FooSANS-Regular" for
    # "Foo Sans") wasn't touched above; give it the new family plus the old suffix.
    if old_ps_name and get_name(font, 6) == old_ps_name:
        old_ps = old_ps_name.partition("-")[0]
        for rec in name.names:
            value = rec.toUnicode()
            if (rec.nameID in POSTSCRIPT_NAME_IDS or rec.nameID == 3 or rec.nameID >= 256) and " " not in value:
                rec.string = value.replace(old_ps, new_ps)
        if "CFF " in font:
            cff = font["CFF "].cff
            cff.fontNames = [n.replace(old_ps, new_ps) for n in cff.fontNames]
    if "CFF " in font:
        cff = font["CFF "].cff
        top = cff.topDictIndex[0]
        cff.fontNames = [n.replace(old_ps, new_ps) for n in cff.fontNames]
        for key in ("FullName", "FamilyName"):
            if value := getattr(top, key, None):
                setattr(top, key, value.replace(old, new))

    if old in new or old_ps in new_ps:
        return []
    leftovers = sorted({r.nameID for r in name.names if r.nameID in FAMILY_NAME_IDS
                        and (old in r.toUnicode() or old_ps in r.toUnicode())})
    if leftovers:
        return [f"name ID(s) {', '.join(map(str, leftovers))} still mention '{old}'; check the result"]
    return []


def _is_english(rec) -> bool:
    return (rec.platformID, rec.langID) in ((3, 0x409), (1, 0)) or rec.platformID == 0


def weight_name(w: float) -> str:
    return WEIGHT_NAMES.get(int(w), f"W{w:g}") if w == int(w) else f"W{w:g}"


def width_name(v: float) -> str:
    for value, name in WIDTHS:
        if v == value:
            return name
    return f"Wdth{v:g}"


def width_class(v: float) -> int:
    return min(range(len(WIDTHS)), key=lambda i: abs(WIDTHS[i][0] - v)) + 1


def axis_label(tag: str, v: float) -> str:
    """Style fragment for an extra axis, e.g. opsz 32 → 'Opsz32', MONO 1 → 'MONO1'."""
    return f"{tag.capitalize() if tag.islower() else tag}{v:g}"


def normalize_style(style: str) -> str:
    """Drop 'Regular' when other words carry the style: 'Condensed Regular' → 'Condensed'."""
    words = [w for w in style.split() if w != "Regular"]
    return " ".join(words) or "Regular"


def style_from_location(loc: dict[str, float], labeled: set[str], italic_file: bool) -> str:
    """Compose a style like 'Condensed Bold Italic' from axis values. `labeled` lists
    extra axes that take several values in this run and so need a label."""
    parts = []
    if "wdth" in loc and (wn := width_name(loc["wdth"])):
        parts.append(wn)
    parts.append(weight_name(loc["wght"]) if "wght" in loc else "Regular")
    parts += [axis_label(t, loc[t]) for t in sorted(labeled - {"wght", "wdth", "ital"}) if t in loc]
    if italic_file or loc.get("ital", 0) >= 0.5:
        parts.append("Italic")
    elif loc.get("slnt", 0) != 0:
        parts.append("Oblique")
    return normalize_style(" ".join(parts))


def apply_style_name(style_name: str, italic: bool) -> str:
    """--style-name override; italic files get 'Italic' appended ('Regular' → 'Italic')."""
    if italic and "Italic" not in style_name.split():
        style_name = f"{style_name} Italic"
    return normalize_style(style_name)


def set_static_names(font: TTFont, family: str, style: str, weight_class: int, width_cls: int | None = None) -> str:
    """Write name records, OS/2 classes and style bits for a static instance and
    return its PostScript name.

    Style linking follows the common convention: ID 2 holds only the Regular /
    Bold / Italic part, everything else joins the family in ID 1, so Bold and
    Italic link within each width ('Condensed Bold' → ID 1 'Family Condensed',
    ID 2 'Bold'). IDs 16/17 hold the full family and style when they differ.
    """
    words = style.split()
    bold = "Bold" in words
    italic = "Italic" in words
    oblique = "Oblique" in words
    legacy_family, legacy_style = legacy_names(family, style)
    ps = ps_name(family, style)

    name = font["name"]
    name.names = [r for r in name.names if r.platformID == 3 and r.nameID not in (16, 17, 21, 22, 25)]
    _set(name, legacy_family, 1)
    _set(name, legacy_style, 2)
    if (legacy_family, legacy_style) != (family, style):
        _set(name, family, 16)
        _set(name, style, 17)
    _set(name, f"{font['head'].fontRevision:.3f};{ps}", 3)
    _set(name, f"{family} {style}", 4)
    _set(name, ps, 6)

    os2 = font["OS/2"]
    os2.usWeightClass = max(1, min(1000, weight_class))
    if width_cls is not None:
        os2.usWidthClass = width_cls
    os2.fsSelection &= ~(1 | 1 << 5 | 1 << 6 | 1 << 9)
    os2.fsSelection |= (1 if italic or oblique else 0) | (1 << 5 if bold else 0) | (1 << 9 if oblique else 0)
    if not (italic or oblique or bold):
        os2.fsSelection |= 1 << 6
    font["head"].macStyle = (1 if bold else 0) | (2 if italic or oblique else 0)
    return ps


def legacy_names(family: str, style: str) -> tuple[str, str]:
    """(name ID 1, name ID 2): ID 2 keeps only Regular / Bold / Italic, every other
    style word joins the family in ID 1."""
    words = style.split()
    rest = " ".join(w for w in words if w not in LINKED_WORDS)
    linked = [w for w, on in (("Bold", "Bold" in words), ("Italic", "Italic" in words or "Oblique" in words)) if on]
    return (f"{family} {rest}" if rest else family), (" ".join(linked) or "Regular")


def set_fixed_pitch(font: TTFont) -> None:
    """Mark a static font as monospaced when every character has the same width -
    zero-width marks and double-width glyphs (e.g. an ffi ligature) aside - as apps
    that only list monospace fonts check this."""
    widths = [font["hmtx"][g][0] for g in set(font.getBestCmap().values())]
    common = max(set(widths), key=widths.count, default=0)
    mono = common > 0 and set(widths) <= {0, common, 2 * common}
    font["post"].isFixedPitch = int(mono)
    panose = font["OS/2"].panose
    if panose.bFamilyType == 2:  # Latin text: bProportion 9 means monospaced
        if mono:
            panose.bProportion = 9
        elif panose.bProportion == 9:
            panose.bProportion = 0


def _set(name_table, value: str, name_id: int) -> None:
    name_table.setName(value, name_id, 3, 1, 0x409)
