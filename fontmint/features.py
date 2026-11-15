"""Listing, freezing and disabling OpenType features.

Freezing makes a feature's substitutions the default by pointing the character map
(cmap) at the substituted glyphs, the same result a text engine gives with the
feature turned on. Only one-to-one substitutions can be frozen this way: single
(GSUB type 1) and alternate (type 3) lookups, and the entries of multiple
substitutions (type 2) that produce a single glyph.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables

from .common import FontmintError

CONTEXTUAL_TYPES = {5, 6, 8}  # contextual, chained contextual, reverse chained


@dataclass
class FreezeResult:
    remapped: int = 0  # characters whose glyph changed
    glyph_map: dict[str, str] = field(default_factory=dict)  # old default glyph → frozen glyph
    partial: list[str] = field(default_factory=list)  # features with rules that can't be frozen
    stale_rules: int = 0  # ligature/context lookups that still expect the replaced glyphs
    outputs_changed: int = 0  # other rules' output glyphs now given in their frozen form


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
        elif value.strip().isascii() and value.strip().isdigit() and int(value) >= 1:
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
    default in the cmap, then update the font's other rules so they keep working
    with the frozen glyphs. Returns what changed and what couldn't be done."""
    if isinstance(spec, str):
        spec = parse_features(spec)
    missing = [t for t in spec if t not in list_features(font)]
    if missing:
        raise FontmintError(f"font has no feature(s): {', '.join(missing)} (--list-features shows which it has)")
    gsub = font["GSUB"].table
    lookups = gsub.LookupList.Lookup
    position = _run_positions(gsub)
    result = FreezeResult()

    lookup_value: dict[int, tuple[str, int]] = {}
    for tag, value in spec.items():
        for index in _feature_lookups(gsub, tag):
            lookup_value.setdefault(index, (tag, value))
    maps: list[tuple[int, dict[str, str]]] = []  # (run position, glyph → glyph), in the order engines run them
    partial: set[str] = set()
    most_alternates: dict[str, int] = {}
    for index in sorted(lookup_value, key=lambda i: (position[i], i)):
        tag, value = lookup_value[index]
        mapping, unsupported, alternates = _one_to_one_map(lookups[index], value)
        most_alternates[tag] = max(most_alternates.get(tag, 0), alternates)
        if unsupported:
            partial.add(tag)
        if mapping:
            maps.append((position[index], mapping))
    for tag, value in spec.items():
        if value > 1 and most_alternates[tag] < value:
            offers = f"offers at most {most_alternates[tag]} alternates" if most_alternates[tag] else "has no alternates"
            raise FontmintError(f"{tag} {offers}, so {tag}={value} isn't possible")
    result.partial = sorted(partial)

    def resolve(glyph: str) -> str:
        for _, mapping in maps:
            glyph = mapping.get(glyph, glyph)
        return glyph

    glyph_ids = font.getReverseGlyphMap()
    encoded = {g for table in font["cmap"].tables if table.format != 14
               for cp, g in table.cmap.items() if not _private_use(cp)}
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

    if maps:  # even with no cmap change: the frozen features may still change other rules' output
        first_change = {old: next(p for p, m in maps if old in m) for old in result.glyph_map}
        # A frozen glyph that already has a character of its own (e.g. ² for sups) can't
        # be taught the old glyph's rules: text with that character would change too.
        # Private Use codes don't count; fonts like Inter give every alternate one.
        repairable = {old: new for old, new in result.glyph_map.items() if new not in encoded}
        position = _with_callers(gsub, position)

        def resolve_after(glyph: str, after: int) -> str:
            """What the frozen features (always on now) turn a glyph into, counting
            only the lookups that run after position `after`."""
            for p, mapping in maps:
                if p > after:
                    glyph = mapping.get(glyph, glyph)
            return glyph

        result.outputs_changed = _repair(gsub, position, maps[-1][0], repairable, first_change, resolve_after,
                                         glyph_ids)
        result.stale_rules = _count_stale(gsub, position, result.glyph_map, first_change)
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


def _private_use(codepoint: int) -> bool:
    return 0xE000 <= codepoint <= 0xF8FF or codepoint >= 0xF0000


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


def _one_to_one_map(lookup, value: int) -> tuple[dict[str, str], bool, int]:
    """Glyph → glyph map of a lookup (the first subtable that covers a glyph wins),
    whether it also has rules that aren't one-to-one, and the most alternates any
    glyph offers."""
    mapping: dict[str, str] = {}
    unsupported = False
    most = 0
    for subtable, kind in _subtables(lookup):
        if kind == 1:
            for source, target in subtable.mapping.items():
                mapping.setdefault(source, target)
        elif kind == 2:  # font tools often put one-to-one rules here too; those freeze like type 1
            for source, sequence in subtable.mapping.items():
                if len(sequence) == 1:
                    mapping.setdefault(source, sequence[0])
                else:
                    unsupported = True
        elif kind == 3:
            for source, alternates in subtable.alternates.items():
                most = max(most, len(alternates))
                if value <= len(alternates):
                    mapping.setdefault(source, alternates[value - 1])
        else:
            unsupported = True
    return mapping, unsupported, most


def _run_positions(gsub) -> list[int]:
    """When text engines run each lookup: rvrn (glyph swaps chosen by axis values,
    including feature-variation lookups) before everything else, the rest in
    lookup-list order."""
    position = list(range(len(gsub.LookupList.Lookup)))
    records = gsub.FeatureList.FeatureRecord
    first = set()
    for index, record in enumerate(records):
        if record.FeatureTag == "rvrn":
            first.update(record.Feature.LookupListIndex)
    variations = getattr(gsub, "FeatureVariations", None)
    for variation in getattr(variations, "FeatureVariationRecord", None) or []:
        for sub in variation.FeatureTableSubstitution.SubstitutionRecord:
            if records[sub.FeatureIndex].FeatureTag == "rvrn":
                first.update(sub.Feature.LookupListIndex)
    for index in first:
        position[index] = -1
    return position


def _with_callers(gsub, position: list[int]) -> list[int]:
    """A lookup that context rules call (a nested lookup) runs when its caller runs,
    which can be earlier than its own place in the list."""
    lookups = gsub.LookupList.Lookup
    calls = {i: {n for subtable, kind in _subtables(lk) if kind in (5, 6) for n in _nested_lookups(subtable)}
             for i, lk in enumerate(lookups)}
    position = list(position)
    changed = True
    while changed:
        changed = False
        for caller, nested in calls.items():
            for n in nested:
                if position[caller] < position[n]:
                    position[n] = position[caller]
                    changed = True
    return position


def _repair(gsub, position, last: int, repairable: dict[str, str], first_change: dict[str, int], resolve_after,
            glyph_ids) -> int:
    """Make the font's other rules behave as in the original with the feature on.
    Only rules that ran before the frozen feature are touched; rules that ran after
    already saw the frozen glyphs.

    - Their output is what the frozen feature would have turned it into, as the
      feature is now always on ('&=' → the cv15 form of its ligature).
    - They learn the frozen glyphs where they knew the old ones: substitutions map
      the new glyph like the old one ('zero.slash' → 'zero.tf.slash' for tnum),
      ligatures get a copy with the frozen components ('->' after freezing tnum),
      and context rules list the frozen glyph next to the old one (Inter's raised
      parentheses around a frozen capital).

    Returns how many rule outputs changed."""
    outputs_changed = 0
    for index, lookup in enumerate(gsub.LookupList.Lookup):
        at = position[index]
        if at >= last:
            continue
        pairs = {old: new for old, new in repairable.items() if at < first_change[old]}
        for subtable, kind in _subtables(lookup):
            outputs_changed += _bake_outputs(subtable, kind, lambda g: resolve_after(g, at))
            if not pairs:
                continue
            if kind in (1, 2, 3):
                _repair_substitution(subtable, kind, pairs)
            elif kind == 4:
                _repair_ligature(subtable, pairs)
            elif kind in (5, 6):
                if subtable.Format == 1:
                    _repair_glyph_rules(subtable, kind, pairs, glyph_ids)
                else:
                    _repair_class_and_coverage_rules(subtable, pairs, glyph_ids)
    return outputs_changed


def _bake_outputs(subtable, kind: int, frozen) -> int:
    """Pass a lookup's output glyphs through `frozen`; returns how many changed."""
    changed = 0

    def bake(glyph: str) -> str:
        nonlocal changed
        new = frozen(glyph)
        changed += new != glyph
        return new

    if kind == 1:
        subtable.mapping = {source: bake(target) for source, target in subtable.mapping.items()}
    elif kind == 2:
        subtable.mapping = {source: [bake(g) for g in seq] for source, seq in subtable.mapping.items()}
    elif kind == 3:
        subtable.alternates = {source: [bake(g) for g in alts] for source, alts in subtable.alternates.items()}
    elif kind == 4:
        for ligatures in subtable.ligatures.values():
            for ligature in ligatures:
                ligature.LigGlyph = bake(ligature.LigGlyph)
    return changed


def _repair_substitution(subtable, kind: int, pairs: dict[str, str]) -> None:
    table = subtable.alternates if kind == 3 else subtable.mapping
    for old, new in pairs.items():
        if old in table and new not in table:
            table[new] = table[old]


def _repair_ligature(subtable, pairs: dict[str, str]) -> None:
    additions: dict[str, list[tuple[list[str], str]]] = {}
    for first, ligatures in subtable.ligatures.items():
        for ligature in ligatures:
            components = [first, *ligature.Component]
            mapped = [pairs.get(g, g) for g in components]
            if mapped != components:
                additions.setdefault(mapped[0], []).append((mapped[1:], ligature.LigGlyph))
    for first, items in additions.items():
        existing = subtable.ligatures.setdefault(first, [])
        known = {(tuple(lig.Component), lig.LigGlyph) for lig in existing}
        for components, glyph in items:
            if (tuple(components), glyph) not in known:
                ligature = otTables.Ligature()
                ligature.Component = components
                ligature.CompCount = len(components) + 1
                ligature.LigGlyph = glyph
                existing.append(ligature)
        existing.sort(key=lambda lig: -len(lig.Component))  # longest match first


def _repair_glyph_rules(subtable, kind: int, pairs: dict[str, str], glyph_ids) -> None:
    """Format 1 context rules list exact glyph sequences: add a copy of each rule that
    mentions an old glyph, with the frozen glyph, right after the original rule so
    the rules keep their priority."""
    set_attr, rule_attr, parts = (
        ("SubRuleSet", "SubRule", ("Input",)) if kind == 5
        else ("ChainSubRuleSet", "ChainSubRule", ("Backtrack", "Input", "LookAhead"))
    )
    rule_sets = dict(zip(subtable.Coverage.glyphs, getattr(subtable, set_attr)))
    copies: dict[str, list] = {}
    for first, rule_set in rule_sets.items():
        rules = getattr(rule_set, rule_attr, None) or [] if rule_set else []
        kept = []
        for rule in rules:
            kept.append(rule)
            mapped_first = pairs.get(first, first)
            if mapped_first == first and not any(g in pairs for part in parts for g in getattr(rule, part) or []):
                continue
            clone = copy.deepcopy(rule)
            for part in parts:
                setattr(clone, part, [pairs.get(g, g) for g in getattr(rule, part) or []])
            if mapped_first == first:
                kept.append(clone)
            else:
                copies.setdefault(mapped_first, []).append(clone)
        if rule_set:
            setattr(rule_set, rule_attr, kept)
            setattr(rule_set, f"{rule_attr}Count", len(kept))
    for first, clones in copies.items():
        rule_set = rule_sets.get(first)
        if rule_set is None:
            rule_set = getattr(otTables, set_attr)()
            setattr(rule_set, rule_attr, [])
            rule_sets[first] = rule_set
        rules = getattr(rule_set, rule_attr) + clones
        setattr(rule_set, rule_attr, rules)
        setattr(rule_set, f"{rule_attr}Count", len(rules))
    order = sorted(rule_sets, key=glyph_ids.__getitem__)  # coverage and rule sets must stay aligned and sorted
    subtable.Coverage.glyphs = order
    setattr(subtable, set_attr, [rule_sets[g] for g in order])
    setattr(subtable, f"{set_attr}Count", len(order))


def _repair_class_and_coverage_rules(subtable, pairs: dict[str, str], glyph_ids) -> None:
    """Formats 2 and 3: add the frozen glyph to every coverage and class the old one
    is in - adding a glyph there can't shift anything else."""
    for attr in ("Coverage", "InputCoverage", "BacktrackCoverage", "LookAheadCoverage"):
        coverages = getattr(subtable, attr, None) or []
        for coverage in coverages if isinstance(coverages, list) else [coverages]:  # a list in format 3
            present = set(coverage.glyphs)
            added = {new for old, new in pairs.items() if old in present and new not in present}
            if added:
                coverage.glyphs = sorted(present | added, key=glyph_ids.__getitem__)
    for attr in ("ClassDef", "InputClassDef", "BacktrackClassDef", "LookAheadClassDef"):
        if class_def := getattr(subtable, attr, None):
            for old, new in pairs.items():
                if old in class_def.classDefs and new not in class_def.classDefs:
                    class_def.classDefs[new] = class_def.classDefs[old]


def _nested_lookups(subtable) -> set[int]:
    """Lookup indices a context subtable calls."""
    records = list(getattr(subtable, "SubstLookupRecord", None) or [])  # format 3
    for set_attr, rule_attr in (("SubRuleSet", "SubRule"), ("ChainSubRuleSet", "ChainSubRule"),
                                ("SubClassSet", "SubClassRule"), ("ChainSubClassSet", "ChainSubClassRule")):
        for rule_set in getattr(subtable, set_attr, None) or []:
            for rule in (getattr(rule_set, rule_attr, None) or []) if rule_set else []:
                records += rule.SubstLookupRecord or []
    return {record.LookupListIndex for record in records}


def _count_stale(gsub, position, glyph_map: dict[str, str], first_change: dict[str, int]) -> int:
    """Ligature and context lookups that saw an old glyph before the frozen feature
    replaced it, and still don't know the frozen glyph (e.g. because it has its own
    character, or the rule kind can't be updated). Only lookups of features that
    scripts use by default count; language-specific ones (e.g. Catalan l·l) would
    make the warning noise for most users."""
    default_lookups = _default_lookups(gsub)
    stale = 0
    for index, lookup in enumerate(gsub.LookupList.Lookup):
        if index not in default_lookups:
            continue
        glyphs: set[str] = set()
        for subtable, kind in _subtables(lookup):
            if kind == 4:
                for first, ligatures in subtable.ligatures.items():
                    glyphs.add(first)
                    for ligature in ligatures:
                        glyphs.update(ligature.Component)
            elif kind in CONTEXTUAL_TYPES:
                glyphs |= _referenced_glyphs(subtable)
        if any(old in glyphs and new not in glyphs and position[index] < first_change[old]
               for old, new in glyph_map.items()):
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
