"""Listing and freezing OpenType (GSUB) features."""

from __future__ import annotations

import logging
from types import SimpleNamespace

from fontTools.ttLib import TTFont
from opentype_feature_freezer import RemapByOTL

from .common import FontmintError


def list_features(font: TTFont) -> list[str]:
    if "GSUB" not in font or not font["GSUB"].table.FeatureList:
        return []
    return sorted({r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord})


def parse_features(features: str) -> list[str]:
    """'ss01, zero,' → ['ss01', 'zero']."""
    return [f.strip() for f in features.split(",") if f.strip()]


def freeze_features(font: TTFont, features: str) -> int:
    """Remap the cmap so the given GSUB single/alternate substitutions become the
    default glyphs. Only the cmap changes - outlines, hinting and layout tables
    are untouched. Returns the number of characters remapped."""
    tags = parse_features(features)
    missing = [f for f in tags if f not in list_features(font)]
    if missing:
        raise FontmintError(f"font has no feature(s): {', '.join(missing)} (--list-features shows which it has)")
    before = {u: g for t in font["cmap"].tables for u, g in t.cmap.items()}
    opts = SimpleNamespace(
        inpath="", outpath="unused", features=",".join(tags), script=None, lang=None,
        zapnames=False, suffix=False, usesuffix="", replacenames="",
        info=False, report=False, names=False,
    )
    remapper = RemapByOTL(opts)
    remapper.ttx = font
    # The freezer warns about every alternate glyph without a character, which is normal.
    freezer_log = logging.getLogger("opentype_feature_freezer")
    level = freezer_log.level
    freezer_log.setLevel(logging.ERROR)
    try:
        remapper.remapByOTL()
    finally:
        freezer_log.setLevel(level)
    if not remapper.success:
        raise FontmintError(f"could not freeze features '{features}'")
    after = {u: g for t in font["cmap"].tables for u, g in t.cmap.items()}
    return sum(1 for u in after if before.get(u) != after[u])
