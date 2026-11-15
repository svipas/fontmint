"""Listing, freezing and disabling OpenType features.

Freezing makes a feature's substitutions the default by pointing the character map
(cmap) at the substituted glyphs, the same result a text engine gives with the
feature turned on. Only one-to-one substitutions can be frozen this way: single
(GSUB type 1) and alternate (type 3) lookups.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables

from .common import FontmintError

FREEZABLE_TYPES = {1, 3}  # single and alternate substitution
CONTEXTUAL_TYPES = {5, 6, 8}  # contextual, chained contextual, reverse chained


@dataclass
class FreezeResult:
    remapped: int = 0  # characters whose glyph changed
    glyph_map: dict[str, str] = field(default_factory=dict)  # old default glyph → frozen glyph
    partial: list[str] = field(default_factory=list)  # features with rules that can't be frozen
    stale_rules: int = 0  # contextual lookups that still expect the replaced glyphs


def list_features(font: TTFont, table: str = "GSUB") -> list[str]:
    records = _feature_records(font, table)
    return sorted({r.FeatureTag for r in records})


def parse_features(features: str) -> dict[str, int]:
    """'ss01, cv47=14,' → {'ss01': 1, 'cv47': 14}. The number picks an alternate
    (1 = first), for features that offer several."""
    spec: dict[str, int] = {}
    for item in (f.strip() for f in features.split(",")):
        if not item:
            continue
        tag, _, value = item.partition("=")
        tag = tag.strip()
        if not value:
            number = 1
        elif value.strip().isdigit() and int(value) >= 1:
            number = int(value)
        else:
            raise FontmintError(f"'{item}': the alternate number must be a whole number of at least 1, e.g. cv47=2")
        if not 1 <= len(tag) <= 4:
            raise FontmintError(f"'{tag}' isn't a feature tag; tags have 1-4 characters, e.g. ss01, zero, cv47")
        if tag in spec:
            raise FontmintError(f"feature '{tag}' given twice")
        spec[tag] = number
    return spec


def parse_tags(tags: str) -> list[str]:
    """'liga, calt,' → ['liga', 'calt']."""
    return list(dict.fromkeys(t.strip() for t in tags.split(",") if t.strip()))


def freeze_features(font: TTFont, spec: dict[str, int] | str) -> FreezeResult:
    """Make the features in `spec` ("ss01,cv47=14" or {"ss01": 1, "cv47": 14}) the
    default in the cmap, then repair ligatures whose components were replaced.
    Returns what changed and what couldn't be done."""
    if isinstance(spec, str):
        spec = parse_features(spec)
    missing = [t for t in spec if t not in list_features(font)]
    if missing:
        raise FontmintError(f"font has no feature(s): {', '.join(missing)} (--list-features shows which it has)")
    gsub = font["GSUB"].table
    result = FreezeResult()

    # Lookups run in LookupList order, each once over the text, like a text engine does.
    lookup_value: dict[int, tuple[str, int]] = {}
    for tag, value in spec.items():
        for index in _feature_lookups(gsub, tag):
            lookup_value.setdefault(index, (tag, value))
    maps: list[tuple[int, dict[str, str]]] = []
    partial = set()
    for index in sorted(lookup_value):
        tag, value = lookup_value[index]
        mapping, unsupported = _one_to_one_map(gsub.LookupList.Lookup[index], value)
        if unsupported:
            partial.add(tag)
        if mapping:
            maps.append((index, mapping))
    result.partial = sorted(partial)

    first_change: dict[str, int] = {}  # old glyph → index of the lookup that first replaced it

    def resolve(glyph: str) -> str:
        original = glyph
        for index, mapping in maps:
            if glyph in mapping:
                first_change.setdefault(original, index)
                glyph = mapping[glyph]
        return glyph

    glyph_ids = font.getReverseGlyphMap()
    changed = set()
    done = set()
    for table in font["cmap"].tables:
        if table.format == 14 or id(table.cmap) in done:  # skip variation sequences, and shared maps seen already
            continue
        done.add(id(table.cmap))
        for codepoint, glyph in list(table.cmap.items()):
            new = resolve(glyph)
            if new == glyph:
                continue
            if table.format == 0 and glyph_ids[new] > 255:  # old Mac subtables hold 1-byte glyph IDs only
                continue
            table.cmap[codepoint] = new
            result.glyph_map[glyph] = new
            changed.add(codepoint)
    result.remapped = len(changed)

    if result.glyph_map:
        _repair_ligatures(gsub, result.glyph_map)
        _repair_contextual(gsub, result.glyph_map, first_change, resolve, glyph_ids)
        result.stale_rules = _count_stale_contextual(gsub, result.glyph_map, first_change)
    return result


def disable_features(font: TTFont, tags: list[str]) -> None:
    """Turn features off by emptying their lookup lists (in GSUB and GPOS, including
    feature variations). The feature records stay, so all indices remain valid."""
    present = set(list_features(font, "GSUB")) | set(list_features(font, "GPOS"))
    if missing := [t for t in tags if t not in present]:
        raise FontmintError(f"font has no feature(s): {', '.join(missing)} (--list-features shows which it has)")
    for table_tag in ("GSUB", "GPOS"):
        records = _feature_records(font, table_tag)
        for index, record in enumerate(records):
            if record.FeatureTag in tags:
                _empty(record.Feature)
                variations = getattr(font[table_tag].table, "FeatureVariations", None)
                for variation in getattr(variations, "FeatureVariationRecord", None) or []:
                    for sub in variation.FeatureTableSubstitution.SubstitutionRecord:
                        if sub.FeatureIndex == index:
                            _empty(sub.Feature)


def has_feature_variations(font: TTFont) -> bool:
    return "GSUB" in font and getattr(font["GSUB"].table, "FeatureVariations", None) is not None


def _feature_records(font: TTFont, table: str) -> list:
    if table not in font or not font[table].table.FeatureList:
        return []
    return font[table].table.FeatureList.FeatureRecord


def _feature_lookups(gsub, tag: str) -> list[int]:
    """Lookup indices of a feature, from the feature records that scripts use by
    default (all records with the tag if none is referenced by default)."""
    records = gsub.FeatureList.FeatureRecord
    by_default = set()
    for script in gsub.ScriptList.ScriptRecord if gsub.ScriptList else []:
        if script.Script.DefaultLangSys:  # optional in the spec
            by_default.update(script.Script.DefaultLangSys.FeatureIndex)
    indices = [i for i, r in enumerate(records) if r.FeatureTag == tag]
    chosen = [i for i in indices if i in by_default] or indices
    return sorted({lookup for i in chosen for lookup in records[i].Feature.LookupListIndex})


def _subtables(lookup):
    """(subtable, type) pairs, unwrapping extension lookups (type 7)."""
    for subtable in lookup.SubTable:
        if lookup.LookupType == 7:
            yield subtable.ExtSubTable, subtable.ExtensionLookupType
        else:
            yield subtable, lookup.LookupType


def _one_to_one_map(lookup, value: int) -> tuple[dict[str, str], bool]:
    """Glyph → glyph map of a lookup (the first subtable that covers a glyph wins),
    and whether it also has rules that aren't one-to-one."""
    mapping: dict[str, str] = {}
    unsupported = False
    for subtable, kind in _subtables(lookup):
        if kind == 1:
            for source, target in subtable.mapping.items():
                mapping.setdefault(source, target)
        elif kind == 3:
            for source, alternates in subtable.alternates.items():
                if value <= len(alternates):
                    mapping.setdefault(source, alternates[value - 1])
        else:
            unsupported = True
    return mapping, unsupported


def _repair_ligatures(gsub, glyph_map: dict[str, str]) -> None:
    """Ligatures were defined on the old default glyphs; add the same ligatures for
    the frozen ones, so e.g. '->' still becomes an arrow after freezing tnum."""
    for lookup in gsub.LookupList.Lookup if gsub.LookupList else []:
        for subtable, kind in _subtables(lookup):
            if kind != 4:
                continue
            additions: dict[str, list[tuple[list[str], str]]] = {}
            for first, ligatures in subtable.ligatures.items():
                for ligature in ligatures:
                    components = [first, *ligature.Component]
                    mapped = [glyph_map.get(g, g) for g in components]
                    if mapped != components:
                        additions.setdefault(mapped[0], []).append((mapped[1:], ligature.LigGlyph))
            for first, items in additions.items():
                existing = subtable.ligatures.setdefault(first, [])
                known = {(tuple(lig.Component), lig.LigGlyph) for lig in existing}
                for components, glyph in items:
                    if (tuple(components), glyph) in known:
                        continue
                    ligature = otTables.Ligature()
                    ligature.Component = components
                    ligature.CompCount = len(components) + 1
                    ligature.LigGlyph = glyph
                    existing.append(ligature)
                existing.sort(key=lambda lig: -len(lig.Component))  # longest match first


def _repair_contextual(gsub, glyph_map: dict[str, str], first_change: dict[str, int], resolve, glyph_ids) -> None:
    """Context rules that ran before the frozen feature saw the original glyph; let
    them see the frozen one too, so e.g. Inter's raised parentheses around capitals
    still work for a frozen capital. Only class- and coverage-based rules (formats
    2 and 3) are extended - adding a glyph there can't shift anything else.

    When such a rule replaces the glyph through a nested single substitution
    ('(' → '(.case'), the nested lookup learns the frozen glyph too and gives the
    frozen form of its result ('(.tf' → '(.case.tf'), as the original font did."""
    lookups = gsub.LookupList.Lookup if gsub.LookupList else []
    for index, lookup in enumerate(lookups):
        pairs = [(old, new) for old, new in glyph_map.items() if index < first_change[old]]
        if not pairs:
            continue
        nested = set()
        for subtable, kind in _subtables(lookup):
            if kind not in (5, 6) or subtable.Format not in (2, 3):
                continue
            for attr in ("Coverage", "InputCoverage", "BacktrackCoverage", "LookAheadCoverage"):
                coverages = getattr(subtable, attr, None) or []
                for coverage in coverages if isinstance(coverages, list) else [coverages]:
                    present = set(coverage.glyphs)
                    added = [new for old, new in pairs if old in present and new not in present]
                    if added:
                        coverage.glyphs = sorted(present | set(added), key=glyph_ids.__getitem__)
            for attr in ("ClassDef", "InputClassDef", "BacktrackClassDef", "LookAheadClassDef"):
                if class_def := getattr(subtable, attr, None):
                    for old, new in pairs:
                        if old in class_def.classDefs and new not in class_def.classDefs:
                            class_def.classDefs[new] = class_def.classDefs[old]
            nested |= _nested_lookups(subtable)
        for nested_index in nested:
            for subtable, kind in _subtables(lookups[nested_index]):
                if kind == 1:
                    for old, new in pairs:
                        if old in subtable.mapping and new not in subtable.mapping:
                            subtable.mapping[new] = resolve(subtable.mapping[old])


def _nested_lookups(subtable) -> set[int]:
    """Lookup indices a contextual subtable calls (formats 2 and 3)."""
    records = list(getattr(subtable, "SubstLookupRecord", None) or [])  # format 3
    for attr, rule_attr in (("SubClassSet", "SubClassRule"), ("ChainSubClassSet", "ChainSubClassRule")):
        for rule_set in getattr(subtable, attr, None) or []:
            for rule in (getattr(rule_set, rule_attr, None) or []) if rule_set else []:
                records += rule.SubstLookupRecord or []
    return {record.LookupListIndex for record in records}


def _count_stale_contextual(gsub, glyph_map: dict[str, str], first_change: dict[str, int]) -> int:
    """Contextual lookups that now see a frozen glyph where they used to see the
    original one: they run before the frozen feature did (so the original font
    showed them the old glyph) and mention the old glyph but not the new one.
    Only lookups of features scripts use by default count; language-specific
    ones (e.g. Catalan l·l) would make the warning noise for most users."""
    default_lookups = _default_lookups(gsub)
    stale = 0
    for index, lookup in enumerate(gsub.LookupList.Lookup if gsub.LookupList else []):
        if index not in default_lookups:
            continue
        glyphs: set[str] = set()
        for subtable, kind in _subtables(lookup):
            if kind in CONTEXTUAL_TYPES:
                glyphs |= _referenced_glyphs(subtable)
        if any(old in glyphs and new not in glyphs and index < first_change[old] for old, new in glyph_map.items()):
            stale += 1
    return stale


def _default_lookups(gsub) -> set[int]:
    records = gsub.FeatureList.FeatureRecord
    lookups = set()
    for script in gsub.ScriptList.ScriptRecord if gsub.ScriptList else []:
        if langsys := script.Script.DefaultLangSys:
            for feature_index in langsys.FeatureIndex:
                lookups.update(records[feature_index].Feature.LookupListIndex)
    return lookups


def _referenced_glyphs(subtable) -> set[str]:
    names: set[str] = set()
    for attr in ("Coverage", "InputCoverage", "BacktrackCoverage", "LookAheadCoverage"):
        coverages = getattr(subtable, attr, None) or []
        for coverage in coverages if isinstance(coverages, list) else [coverages]:  # a list in format 3
            names.update(coverage.glyphs)
    for attr in ("ClassDef", "InputClassDef", "BacktrackClassDef", "LookAheadClassDef"):
        if class_def := getattr(subtable, attr, None):
            names.update(class_def.classDefs)
    for attr, rule_attr in (("SubRuleSet", "SubRule"), ("ChainSubRuleSet", "ChainSubRule")):
        for rule_set in getattr(subtable, attr, None) or []:
            for rule in getattr(rule_set, rule_attr, None) or [] if rule_set else []:
                for part in ("Input", "Backtrack", "LookAhead"):
                    names.update(getattr(rule, part, None) or [])
    return names


def _empty(feature) -> None:
    feature.LookupListIndex = []
    feature.LookupCount = 0
