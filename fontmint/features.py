"""Listing, freezing and disabling OpenType features.

Freezing makes a feature's substitutions the default by pointing the character map
(cmap) at the substituted glyphs, the same result a text engine gives with the
feature turned on. Only one-to-one substitutions fit in the cmap: single (GSUB
type 1) and alternate (type 3) lookups, and the entries of multiple substitutions
(type 2) that produce a single glyph. A feature's other lookups are added to calt
or liga, and the font's other rules are updated to work with the frozen glyphs.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables

from .common import FontmintError, get_name

CONTEXTUAL_TYPES = {5, 6, 8}  # contextual, chained contextual, reverse chained
# Scripts whose features text engines apply in a single pass, so a lookup added to calt
# still runs at its place in the lookup list. Arabic or Indic engines run features in
# stages, where moving a lookup to another feature can change when it runs.
SINGLE_PASS_SCRIPTS = {"DFLT", "latn", "grek", "cyrl", "armn", "geor", "hebr"}


@dataclass
class FreezeResult:
    remapped: int = 0  # characters whose glyph changed
    glyph_map: dict[str, str] = field(default_factory=dict)  # old default glyph → frozen glyph
    partial: list[str] = field(default_factory=list)  # features with rules that can't be frozen
    moved: list[str] = field(default_factory=list)  # features whose unfreezable rules were added to calt/liga
    stale_rules: int = 0  # ligature/context lookups that still expect the glyphs from before freezing
    outputs_changed: int = 0  # other rules' output glyphs now given in their frozen form


def list_features(font: TTFont, table: str = "GSUB") -> list[str]:
    records = _feature_records(font, table)
    return sorted({r.FeatureTag for r in records})


def feature_names(font: TTFont) -> dict[str, str]:
    """Names the font gives its stylistic sets and character variants,
    e.g. {'ss02': 'Disambiguation'}."""
    names: dict[str, str] = {}
    for record in _feature_records(font, "GSUB"):
        params = record.Feature.FeatureParams
        name_id = getattr(params, "UINameID", None) or getattr(params, "FeatUILabelNameID", None)
        if name_id and record.FeatureTag not in names and (name := get_name(font, name_id)):
            names[record.FeatureTag] = "".join(c for c in name if c.isprintable())  # untrusted text from the font
    return dict(sorted(names.items()))


def language_tags(font: TTFont) -> list[str]:
    """Languages the font has its own forms for, as OpenType tags, e.g. ['ROM', 'SRB']."""
    scripts = _scripts(font["GSUB"].table) if "GSUB" in font else []
    return sorted({lang.LangSysTag.strip() for script in scripts for lang in script.Script.LangSysRecord})


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


def freeze_features(font: TTFont, spec: dict[str, int] | str, language: str = "") -> FreezeResult:
    """Make the features in `spec` ("ss01,cv47=14" or {"ss01": 1, "cv47": 14}) the
    default in the cmap, then update the font's other rules so they keep working
    with the frozen glyphs. `language` (an OpenType tag such as "ROM") freezes the
    forms the font shows for that language. Returns what changed and what couldn't be done."""
    if isinstance(spec, str):
        spec = parse_features(spec)
    result = FreezeResult()
    if not spec:
        return result
    present = list_features(font)
    if missing := [t for t in spec if t not in present]:
        raise FontmintError(f"font has no feature(s): {', '.join(missing)} (--info shows which it has)")
    gsub = font["GSUB"].table
    if language and language not in language_tags(font):
        raise FontmintError(f"font has no forms for language '{language}' (--info shows its languages)")
    for tag in spec:
        if _feature_lookups(gsub, tag, language):
            continue
        if language:
            raise FontmintError(f"font has no {tag} for language '{language}'")
        records = gsub.FeatureList.FeatureRecord
        if languages := [lang for lang in language_tags(font) if any(
                records[i].FeatureTag == tag for i in _language_features(gsub, lang))]:
            raise FontmintError(f"{tag} only has forms for some languages ({', '.join(languages)}); "
                                "pick one with --language")
    lookups = gsub.LookupList.Lookup
    position = _run_positions(gsub)

    lookup_value: dict[int, tuple[str, int]] = {}
    for tag, value in spec.items():
        for index in _feature_lookups(gsub, tag, language):
            lookup_value.setdefault(index, (tag, value))
    maps: list[tuple[int, dict[str, str]]] = []  # (run position, glyph → glyph), in the order engines run them
    leftover: dict[str, set[int]] = {}  # tag → lookups with rules that can't be frozen
    most_alternates: dict[str, int] = {}
    for index in sorted(lookup_value, key=lambda i: (position[i], i)):
        tag, value = lookup_value[index]
        mapping, unsupported, alternates = _one_to_one_map(lookups[index], value)
        most_alternates[tag] = max(most_alternates.get(tag, 0), alternates)
        if unsupported:
            leftover.setdefault(tag, set()).add(index)
        if mapping:
            maps.append((position[index], mapping))
    for tag, value in spec.items():
        if value > 1 and (most := most_alternates.get(tag, 0)) < value:
            offers = f"offers at most {most} alternates" if most else "has no alternates"
            raise FontmintError(f"{tag} {offers}, so {tag}={value} isn't possible")
    result.partial = sorted(leftover)

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
        position = _with_callers(lookups, position)
        changes: dict[int, dict[str, str]] = {}

        def changes_after(at: int) -> dict[str, str]:
            """What the frozen features (always on now) turn glyphs into, counting only
            the lookups that run after position `at`: a lookup at `at` that saw the
            first glyph in the original sees the second one in the frozen font."""
            if at not in changes:
                later = [mapping for p, mapping in maps if p > at]
                changes[at] = {}
                for glyph in {g for mapping in later for g in mapping}:
                    new = glyph
                    for mapping in later:
                        new = mapping.get(new, new)
                    if new != glyph:
                        changes[at][glyph] = new
            return changes[at]

        # A frozen glyph that already has a character of its own (e.g. ² for sups) can't
        # be taught the old glyph's rules: text with that character would change too.
        # Private Use codes don't count; fonts like Inter give every alternate one.
        result.outputs_changed = _repair(lookups, position, changes_after, encoded, glyph_ids)
        result.stale_rules = _count_stale(gsub, position, changes_after)
    result.moved = [tag for tag in result.partial if _move_to_calt(gsub, tag, leftover[tag], spec[tag])]
    return result


def _move_to_calt(gsub, tag: str, indices: set[int], value: int) -> bool:
    """Add a frozen feature's lookups that can't be frozen to calt (or liga, if a script
    has no calt), in the scripts that use the feature. Apps turn both on by default,
    but usually off together with ligatures. The lookups keep their place in the
    lookup list, so they run as in the original with the feature on. Returns whether
    any were added."""
    lookups = gsub.LookupList.Lookup
    if value > 1:  # apps would pick the first alternate of any alternate lookup these call
        indices = {i for i in indices
                   if not any(kind == 3 for n in _called(lookups, i) for _, kind in _subtables(lookups[n]))}
    records = gsub.FeatureList.FeatureRecord
    targets, staged = set(), set()
    for script in _scripts(gsub):
        systems = [script.Script.DefaultLangSys] if script.Script.DefaultLangSys else []
        systems += [lang.LangSys for lang in script.Script.LangSysRecord]
        features = {i for system in systems for i in system.FeatureIndex}
        if script.ScriptTag not in SINGLE_PASS_SCRIPTS:
            staged |= features
        elif any(records[i].FeatureTag == tag for i in features):
            for host in ("calt", "liga"):  # both on by default; liga for fonts without calt (e.g. Recursive)
                if found := {i for i in features if records[i].FeatureTag == host}:
                    targets |= found
                    break
    targets -= staged  # a calt that e.g. Arabic shares would run the lookups there too
    if not indices or not targets:
        return False
    features = [records[i].Feature for i in targets]
    features += [sub.Feature for sub in _variation_substitutions(gsub) if sub.FeatureIndex in targets]
    added = False
    for feature in features:
        if not indices <= set(feature.LookupListIndex):  # e.g. not when freezing liga itself
            feature.LookupListIndex = sorted(set(feature.LookupListIndex) | indices)
            feature.LookupCount = len(feature.LookupListIndex)
            added = True
    return added


def _calls(lookup) -> set[int]:
    """Lookups that a lookup's context rules call (nested lookups)."""
    return {n for subtable, kind in _subtables(lookup) if kind in (5, 6) for n in _nested_lookups(subtable)}


def _called(lookups, index: int) -> set[int]:
    """A lookup and every lookup its context rules call, directly or not."""
    seen, todo = set(), [index]
    while todo:
        i = todo.pop()
        if i not in seen:
            seen.add(i)
            todo += _calls(lookups[i])
    return seen


def _variation_substitutions(table) -> list:
    """The alternate feature tables that feature variations switch to at some axis values."""
    variations = getattr(table, "FeatureVariations", None)
    return [sub for variation in getattr(variations, "FeatureVariationRecord", None) or []
            if variation.FeatureTableSubstitution
            for sub in variation.FeatureTableSubstitution.SubstitutionRecord]


def disable_features(font: TTFont, tags: list[str]) -> None:
    """Turn features off by emptying their lookup lists (in GSUB and GPOS, including
    feature variations). The feature records stay, so all indices remain valid."""
    present = set(list_features(font, "GSUB")) | set(list_features(font, "GPOS"))
    if missing := [t for t in tags if t not in present]:
        raise FontmintError(f"font has no feature(s): {', '.join(missing)} (--info shows which it has)")
    for table_tag in ("GSUB", "GPOS"):
        records = _feature_records(font, table_tag)
        if not records:
            continue
        for record in records:
            if record.FeatureTag in tags:
                _empty(record.Feature)
        for sub in _variation_substitutions(font[table_tag].table):
            if records[sub.FeatureIndex].FeatureTag in tags:
                _empty(sub.Feature)


def _private_use(codepoint: int) -> bool:
    return 0xE000 <= codepoint <= 0xF8FF or codepoint >= 0xF0000


def _feature_records(font: TTFont, table: str) -> list:
    if table not in font or not font[table].table.FeatureList:
        return []
    return font[table].table.FeatureList.FeatureRecord


def _feature_lookups(gsub, tag: str, language: str = "") -> list[int]:
    """Lookup indices of a feature, from the feature records text engines use: in each
    script those of `language`, or of the default language system if the script
    doesn't have that language. A font without any default language system (they
    are optional) gives all records with the tag."""
    records = gsub.FeatureList.FeatureRecord
    indices = [i for i, r in enumerate(records) if r.FeatureTag == tag]
    systems = []
    for script in _scripts(gsub):
        own = [lang.LangSys for lang in script.Script.LangSysRecord if lang.LangSysTag.strip() == language]
        systems += own if language and own else [script.Script.DefaultLangSys]
    if any(systems):
        used = {i for system in systems if system for i in system.FeatureIndex}
        indices = [i for i in indices if i in used]
    return sorted({lookup for i in indices for lookup in records[i].Feature.LookupListIndex})


def _scripts(gsub) -> list:
    return gsub.ScriptList.ScriptRecord if gsub.ScriptList else []


def _language_features(gsub, language: str) -> set[int]:
    return {i for script in _scripts(gsub) for lang in script.Script.LangSysRecord
            if lang.LangSysTag.strip() == language for i in lang.LangSys.FeatureIndex}


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
    features = [r.Feature for r in records if r.FeatureTag == "rvrn"]
    features += [sub.Feature for sub in _variation_substitutions(gsub) if records[sub.FeatureIndex].FeatureTag == "rvrn"]
    for feature in features:
        for index in feature.LookupListIndex:
            position[index] = -1
    return position


def _with_callers(lookups, position: list[int]) -> list[int]:
    """A lookup that context rules call (a nested lookup) runs when its caller runs,
    which can be earlier than its own place in the list."""
    calls = {i: _calls(lookup) for i, lookup in enumerate(lookups)}
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


def _repair(lookups, position: list[int], changes_after, encoded: set[str], glyph_ids) -> int:
    """Make the font's other rules behave as in the original with the feature on.
    Only rules that ran before a frozen lookup are touched; rules that ran after
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
    for index, lookup in enumerate(lookups):
        frozen = changes_after(position[index])
        if not frozen:
            continue
        pairs = {old: new for old, new in frozen.items() if new not in encoded}
        for subtable, kind in _subtables(lookup):
            outputs_changed += _bake_outputs(subtable, kind, lambda glyph: frozen.get(glyph, glyph))
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
            elif kind == 8:
                _repair_reverse_rules(subtable, pairs, glyph_ids)
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
    elif kind == 8:
        subtable.Substitute = [bake(g) for g in subtable.Substitute]
    return changed


def _repair_substitution(subtable, kind: int, pairs: dict[str, str]) -> None:
    table = subtable.alternates if kind == 3 else subtable.mapping
    for old, new in pairs.items():
        if old in table and new not in table:
            table[new] = table[old]


def _repair_ligature(subtable, pairs: dict[str, str]) -> None:
    """Add a copy of each ligature that has an old glyph among its components, with
    the frozen glyphs. The first ligature that matches wins, so a copy goes right
    after its original; under another first glyph, it goes before shorter ligatures."""
    moved: dict[str, list] = {}
    for first, ligatures in subtable.ligatures.items():
        own = {tuple(ligature.Component) for ligature in ligatures}
        kept = []
        for ligature in ligatures:
            kept.append(ligature)
            components = [first, *ligature.Component]
            mapped = [pairs.get(g, g) for g in components]
            if mapped == components:
                continue
            clone = otTables.Ligature()
            clone.Component = mapped[1:]
            clone.CompCount = len(mapped)
            clone.LigGlyph = ligature.LigGlyph
            if mapped[0] != first:
                moved.setdefault(mapped[0], []).append(clone)
            elif tuple(clone.Component) not in own:
                kept.append(clone)
        ligatures[:] = kept
    for first, clones in moved.items():
        existing = subtable.ligatures.setdefault(first, [])
        for clone in clones:
            if tuple(clone.Component) in {tuple(ligature.Component) for ligature in existing}:
                continue
            shorter = (i for i, ligature in enumerate(existing) if len(ligature.Component) < len(clone.Component))
            existing.insert(next(shorter, len(existing)), clone)


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
        rules = (getattr(rule_set, rule_attr, None) or []) if rule_set else []
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


def _repair_reverse_rules(subtable, pairs: dict[str, str], glyph_ids) -> None:
    """Reverse chaining rules (type 8) pair each input glyph with its substitute:
    the frozen glyph gets the old one's substitute, and joins the context coverages."""
    substitutes = dict(zip(subtable.Coverage.glyphs, subtable.Substitute))
    for old, new in pairs.items():
        if old in substitutes and new not in substitutes:
            substitutes[new] = substitutes[old]
    order = sorted(substitutes, key=glyph_ids.__getitem__)  # coverage and substitutes must stay aligned and sorted
    subtable.Coverage.glyphs = order
    subtable.Substitute = [substitutes[g] for g in order]
    subtable.GlyphCount = len(order)
    _repair_class_and_coverage_rules(subtable, pairs, glyph_ids)  # the input coverage is complete, so left alone


def _nested_lookups(subtable) -> set[int]:
    """Lookup indices a context subtable calls."""
    records = list(getattr(subtable, "SubstLookupRecord", None) or [])  # format 3
    for set_attr, rule_attr in (("SubRuleSet", "SubRule"), ("ChainSubRuleSet", "ChainSubRule"),
                                ("SubClassSet", "SubClassRule"), ("ChainSubClassSet", "ChainSubClassRule")):
        for rule_set in getattr(subtable, set_attr, None) or []:
            for rule in (getattr(rule_set, rule_attr, None) or []) if rule_set else []:
                records += rule.SubstLookupRecord or []
    return {record.LookupListIndex for record in records}


def _count_stale(gsub, position: list[int], changes_after) -> int:
    """Ligature and context lookups that saw a glyph before a frozen feature replaced
    it, and still don't know the frozen glyph (e.g. because it has its own character).
    Only lookups of features that scripts use by default count; language-specific
    ones (e.g. Catalan l·l) would make the warning noise for most users."""
    lookups = gsub.LookupList.Lookup
    stale = 0
    for index in sorted({n for i in _default_lookups(gsub) for n in _called(lookups, i)}):
        glyphs: set[str] = set()
        for subtable, kind in _subtables(lookups[index]):
            if kind == 4:
                for first, ligatures in subtable.ligatures.items():
                    glyphs.add(first)
                    for ligature in ligatures:
                        glyphs.update(ligature.Component)
            elif kind in CONTEXTUAL_TYPES:
                glyphs |= _referenced_glyphs(subtable)
        if any(old in glyphs and new not in glyphs for old, new in changes_after(position[index]).items()):
            stale += 1
    return stale


def _default_lookups(gsub) -> set[int]:
    records = gsub.FeatureList.FeatureRecord
    lookups = set()
    for script in _scripts(gsub):
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
            for rule in (getattr(rule_set, rule_attr, None) or []) if rule_set else []:
                for part in ("Input", "Backtrack", "LookAhead"):
                    names.update(getattr(rule, part, None) or [])
    return names


def _empty(feature) -> None:
    feature.LookupListIndex = []
    feature.LookupCount = 0
