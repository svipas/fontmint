import unittest

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib.tables import otTables

from fontmint.common import FontmintError
from fontmint.features import (
    disable_features,
    feature_names,
    freeze_features,
    language_tags,
    list_features,
    parse_features,
)

from . import fixtures as fx


class FeaturesTest(unittest.TestCase):
    def test_list(self):
        font = fx.open_font(fx.static_ttf())
        self.assertEqual(list_features(font), ["liga", "ss01"])
        self.assertEqual(feature_names(font), {"ss01": "Slashed zero"})

    def test_freeze_remaps_cmap(self):
        font = fx.open_font(fx.static_ttf())
        self.assertEqual(freeze_features(font, "ss01").remapped, 2)
        cmap = font.getBestCmap()
        self.assertEqual(cmap[ord("0")], "zero.ss01")
        self.assertEqual(cmap[ord("I")], "I.ss01")
        self.assertEqual(cmap[ord("H")], "H")

    def test_freeze_works_on_variable_and_cff(self):
        for data in (fx.variable_ttf(), fx.static_otf()):
            font = fx.open_font(data)
            freeze_features(font, "ss01")
            self.assertEqual(font.getBestCmap()[ord("0")], "zero.ss01")

    def test_ligatures_dont_change_the_cmap(self):
        self.assertEqual(freeze_features(fx.open_font(fx.static_ttf()), "liga").remapped, 0)
        self.assertEqual(freeze_features(fx.open_font(fx.static_ttf()), "").remapped, 0)

    def test_spaces_and_trailing_commas(self):
        font = fx.open_font(fx.static_ttf())
        self.assertEqual(freeze_features(font, " ss01 , ").remapped, 2)
        with self.assertRaisesRegex(FontmintError, r"feature\(s\): ss02 \("):
            freeze_features(font, "ss01, ss02")

    def test_parse_alternate_numbers(self):
        self.assertEqual(parse_features("ss01, cv47=14"), {"ss01": 1, "cv47": 14})
        for bad in ("cv47=0", "cv47=x", "ss01,ss01", "toolong"):
            with self.subTest(spec=bad), self.assertRaises(FontmintError):
                parse_features(bad)

    def test_missing_feature(self):
        with self.assertRaisesRegex(FontmintError, "no feature.*ss02"):
            freeze_features(fx.open_font(fx.static_ttf()), "ss01,ss02")



def with_features(fea: str, base: bytes | None = None):
    """A copy of the static fixture whose GSUB is built from `fea`."""
    font = fx.open_font(base or fx.static_ttf(hinted=False))
    del font["GSUB"]
    addOpenTypeFeaturesFromString(font, fea)
    return font


class FreezeOrderTest(unittest.TestCase):
    """The frozen font must show what a text engine shows with the feature on."""

    def one_lookup(self, mapping: dict) -> object:
        """Fixture font whose ss01 is a single lookup with exactly `mapping` (feaLib
        would split these rules into several lookups)."""
        font = fx.open_font(fx.static_ttf())
        gsub = font["GSUB"].table
        index = next(r for r in gsub.FeatureList.FeatureRecord if r.FeatureTag == "ss01").Feature.LookupListIndex[0]
        gsub.LookupList.Lookup[index].SubTable[0].mapping = dict(mapping)
        return font

    def test_swap_in_one_lookup(self):
        font = self.one_lookup({"H": "O", "O": "H"})
        freeze_features(font, "ss01")
        cmap = font.getBestCmap()
        self.assertEqual((cmap[ord("H")], cmap[ord("O")]), ("O", "H"))

    def test_chain_in_one_lookup_applies_once(self):
        font = self.one_lookup({"H": "O", "O": "o"})
        freeze_features(font, "ss01")
        self.assertEqual(font.getBestCmap()[ord("H")], "O")  # not o: one lookup runs once

    def test_lookups_apply_in_order(self):
        font = with_features("feature ss02 { lookup A { sub H by O; } A; lookup B { sub O by o; } B; } ss02;")
        freeze_features(font, "ss02")
        self.assertEqual(font.getBestCmap()[ord("H")], "o")

    def test_pick_an_alternate(self):
        fea = "feature cv01 { sub zero from [zero.ss01 O o]; } cv01;"
        for number, expected in ((1, "zero.ss01"), (2, "O"), (3, "o")):
            with self.subTest(number=number):
                font = with_features(fea)
                freeze_features(font, f"cv01={number}")
                self.assertEqual(font.getBestCmap()[ord("0")], expected)
        with self.assertRaisesRegex(FontmintError, "cv01 offers at most 3 alternates"):
            freeze_features(with_features(fea), "cv01=4")
        with self.assertRaisesRegex(FontmintError, "ss01 has no alternates"):
            freeze_features(fx.open_font(fx.static_ttf()), "ss01=2")

    def test_script_without_default_language_system(self):
        font = fx.open_font(fx.static_ttf())
        for record in font["GSUB"].table.ScriptList.ScriptRecord:
            record.Script.DefaultLangSys = None
        self.assertEqual(freeze_features(font, "ss01").remapped, 2)

    def test_language_forms(self):
        fea = ("languagesystem DFLT dflt; languagesystem latn dflt; languagesystem latn ROM;"
               "feature locl { script latn; language ROM exclude_dflt; sub I by I.ss01; } locl;"
               "feature ss01 { sub zero by zero.ss01; } ss01;")
        self.assertEqual(language_tags(with_features(fea)), ["ROM"])
        with self.assertRaisesRegex(FontmintError, r"locl only has forms for some languages \(ROM\); pick one"):
            freeze_features(with_features(fea), "locl")
        font = with_features(fea)
        self.assertEqual(freeze_features(font, "locl", "ROM").remapped, 1)
        self.assertEqual(font.getBestCmap()[ord("I")], "I.ss01")
        with self.assertRaisesRegex(FontmintError, "no forms for language 'TRK'"):
            freeze_features(with_features(fea), "locl", "TRK")
        font = with_features(fea)
        records = font["GSUB"].table.FeatureList.FeatureRecord
        scripts = {record.ScriptTag: record.Script for record in font["GSUB"].table.ScriptList.ScriptRecord}
        romanian = scripts["latn"].LangSysRecord[0].LangSys
        romanian.FeatureIndex = [i for i in romanian.FeatureIndex if records[i].FeatureTag != "ss01"]
        self.assertEqual(freeze_features(font, "ss01", "ROM").remapped, 1)  # a script without Romanian uses its default
        font = with_features(fea.replace("languagesystem DFLT dflt;", ""))
        records = font["GSUB"].table.FeatureList.FeatureRecord
        romanian = font["GSUB"].table.ScriptList.ScriptRecord[0].Script.LangSysRecord[0].LangSys
        romanian.FeatureIndex = [i for i in romanian.FeatureIndex if records[i].FeatureTag != "ss01"]
        with self.assertRaisesRegex(FontmintError, "no ss01 for language 'ROM'"):
            freeze_features(font, "ss01", "ROM")

    def test_old_mac_cmap_is_left_alone_for_high_glyph_ids(self):
        font = fx.open_font(fx.mac_cmap_ttf())
        freeze_features(font, "ss01")
        mac = next(t for t in font["cmap"].tables if t.format == 0)
        self.assertEqual(mac.cmap[ord("0")], "zero")  # zero.ss01 doesn't fit in a format 0 subtable
        self.assertEqual(font.getBestCmap()[ord("0")], "zero.ss01")
        fx._save(font)  # used to fail with OverflowError


class FreezeRepairTest(unittest.TestCase):
    def ligatures_after_freezing(self, fea: str) -> dict:
        font = with_features(fea)
        freeze_features(font, "ss01")
        lookup = next(lk for lk in font["GSUB"].table.LookupList.Lookup if lk.LookupType == 4)
        return lookup.SubTable[0].ligatures

    def test_ligature_before_the_frozen_feature_follows(self):
        ligatures = self.ligatures_after_freezing("feature liga { sub I zero by H; } liga;"
                                                  "feature ss01 { sub zero by zero.ss01; sub I by I.ss01; } ss01;")
        self.assertEqual([(lig.Component, lig.LigGlyph) for lig in ligatures["I.ss01"]], [(["zero.ss01"], "H")])
        self.assertIn("I", ligatures)  # the original ligature stays

    def test_ligature_after_the_frozen_feature_stays(self):
        # the original font with ss01 on never forms this ligature (it sees I.ss01 zero.ss01)
        ligatures = self.ligatures_after_freezing("feature ss01 { sub zero by zero.ss01; sub I by I.ss01; } ss01;"
                                                  "feature liga { sub I zero by H; } liga;")
        self.assertNotIn("I.ss01", ligatures)

    def test_frozen_glyph_with_its_own_character_is_not_repaired(self):
        # O is typed directly too: teaching the ligature "I O" would change text without the frozen '0'
        font = with_features("feature liga { sub I zero by H; } liga; feature ss01 { sub zero by O; } ss01;")
        result = freeze_features(font, "ss01")
        lookup = next(lk for lk in font["GSUB"].table.LookupList.Lookup if lk.LookupType == 4)
        self.assertEqual(list(lookup.SubTable[0].ligatures["I"][0].Component), ["zero"])
        self.assertEqual(len(lookup.SubTable[0].ligatures["I"]), 1)
        self.assertEqual(result.stale_rules, 1)

    def test_earlier_single_substitution_learns_frozen_glyph(self):
        # tnum runs before zero: the original shows zero.tf.slash for tnum + zero
        font = with_features("feature tnum { sub zero by O; } tnum;"
                             "feature zero { sub zero by zero.ss01; sub O by o; } zero;")
        freeze_features(font, "zero")
        tnum = font["GSUB"].table.LookupList.Lookup[0].SubTable[0]
        self.assertEqual(tnum.mapping.get("zero.ss01"), "o")

    def test_glyph_sequence_rules_get_a_copy(self):
        # several exact-glyph rules make feaLib build format 1; all run before ss01
        font = with_features("lookup LOWER { sub O by o; } LOWER;"
                             "feature calt { sub O' lookup LOWER I; sub O' lookup LOWER x; sub H' lookup LOWER I n; } calt;"
                             "feature ss01 { sub I by I.ss01; } ss01;")
        chain = font["GSUB"].table.LookupList.Lookup[1].SubTable[0]
        self.assertEqual(chain.Format, 1)
        result = freeze_features(font, "ss01")
        rule_sets = dict(zip(chain.Coverage.glyphs, chain.ChainSubRuleSet))
        o_rules = [list(r.LookAhead) for r in rule_sets["O"].ChainSubRule]
        self.assertEqual(o_rules[:2], [["I"], ["I.ss01"]])  # the copy right after the original keeps priority
        self.assertIn(["I.ss01", "n"], [list(r.LookAhead) for r in rule_sets["H"].ChainSubRule])
        self.assertEqual(result.stale_rules, 0)

    def test_context_rules_see_frozen_glyphs(self):
        # calt (before ss01) turns O into o when I follows; after freezing ss01 it must also fire before I.ss01
        font = with_features("lookup LOWER { sub O by o; } LOWER;"
                             "feature calt { sub O' lookup LOWER I; } calt;"
                             "feature ss01 { sub I by I.ss01; } ss01;")
        result = freeze_features(font, "ss01")
        chain = font["GSUB"].table.LookupList.Lookup[1].SubTable[0]
        self.assertIn("I.ss01", chain.LookAheadCoverage[0].glyphs)
        self.assertEqual(result.stale_rules, 0)

    def test_nested_substitution_learns_frozen_glyph(self):
        # calt replaces I by H before O; ss01 freezes I → I.ss01, so I.ss01 must become H there too
        font = with_features("lookup TOH { sub I by H; } TOH;"
                             "feature calt { sub I' lookup TOH O; } calt;"
                             "feature ss01 { sub I by I.ss01; } ss01;")
        freeze_features(font, "ss01")
        nested = font["GSUB"].table.LookupList.Lookup[0].SubTable[0]
        self.assertEqual(nested.mapping.get("I.ss01"), "H")

    def test_rules_between_two_frozen_steps_learn_the_final_glyph(self):
        # calt sits between what makes zero.ss01 and what freezes it into I.ss01
        calt = "feature calt { sub zero.ss01 x' by n; } calt;"
        for spec, fea in (
            ("ss01", "feature liga { sub H O by zero.ss01; } liga;" + calt + "feature ss01 { sub zero.ss01 by I.ss01; } ss01;"),
            ("ss01,ss02", "feature ss01 { sub zero by zero.ss01; } ss01;" + calt
                          + "feature ss02 { sub zero.ss01 by I.ss01; } ss02;"),
        ):
            with self.subTest(spec=spec):
                font = with_features(fea)
                result = freeze_features(font, spec)
                chain = next(lk for lk in font["GSUB"].table.LookupList.Lookup if lk.LookupType == 6).SubTable[0]
                self.assertEqual(chain.BacktrackCoverage[0].glyphs, ["zero.ss01", "I.ss01"])
                self.assertEqual(result.stale_rules, 0)

    def test_ligature_copies_keep_the_font_s_order(self):
        font = with_features("feature liga { sub I zero by H; sub I zero O by x; } liga;"
                             "feature ss01 { sub zero by zero.ss01; } ss01;")
        ligatures = font["GSUB"].table.LookupList.Lookup[0].SubTable[0].ligatures
        ligatures["I"].reverse()  # shorter first: the longer one never matches, and must not start to
        freeze_features(font, "ss01")
        self.assertEqual([list(lig.Component) for lig in ligatures["I"]],
                         [["zero"], ["zero.ss01"], ["zero", "O"], ["zero.ss01", "O"]])

    def test_reverse_chaining_rules_are_updated(self):
        font = with_features("feature calt { rsub I I' by zero; } calt;"
                             "feature ss01 { sub zero by zero.ss01; sub I by I.ss01; } ss01;")
        result = freeze_features(font, "ss01")
        rule = font["GSUB"].table.LookupList.Lookup[0].SubTable[0]
        self.assertEqual((rule.Coverage.glyphs, rule.Substitute), (["I", "I.ss01"], ["zero.ss01", "zero.ss01"]))
        self.assertEqual(rule.BacktrackCoverage[0].glyphs, ["I", "I.ss01"])
        self.assertEqual((result.outputs_changed, result.stale_rules), (1, 0))
        fx.open_font(fx._save(font))["GSUB"].ensureDecompiled()

    def test_one_glyph_entries_of_multiple_substitutions_freeze(self):
        # one rule produces two glyphs, so the whole lookup is a multiple substitution (type 2)
        font = with_features("feature ss04 { sub zero by zero.ss01; sub I by I.ss01; sub H by I O; } ss04;")
        self.assertEqual(font["GSUB"].table.LookupList.Lookup[0].LookupType, 2)
        result = freeze_features(font, "ss04")
        cmap = font.getBestCmap()
        self.assertEqual((cmap[ord("0")], cmap[ord("I")], cmap[ord("H")]), ("zero.ss01", "I.ss01", "H"))
        self.assertEqual((result.remapped, result.partial), (2, ["ss04"]))

    def test_unfreezable_rules_move_to_calt(self):
        # "I before zero" depends on the next character, so the cmap can't hold it; calt runs it instead
        rules = "feature ss03 { sub zero by zero.ss01; sub I' zero by I.ss01; } ss03;"
        for host, fea in (("calt", "feature calt { sub O' I by o; } calt;"), ("liga", "feature liga { sub I O by H; } liga;")):
            with self.subTest(host=host):
                font = with_features(fea + rules)
                result = freeze_features(font, "ss03")
                self.assertEqual((result.partial, result.moved), (["ss03"], ["ss03"]))
                ss03 = set(next(r for r in font["GSUB"].table.FeatureList.FeatureRecord
                                if r.FeatureTag == "ss03").Feature.LookupListIndex)
                record = next(r for r in font["GSUB"].table.FeatureList.FeatureRecord if r.FeatureTag == host)
                contextual = {i for i in ss03 if font["GSUB"].table.LookupList.Lookup[i].LookupType == 6}
                self.assertTrue(contextual and contextual <= set(record.Feature.LookupListIndex))

    def test_rules_stay_put_where_moving_could_change_their_order(self):
        rules = "feature ss03 { sub zero by zero.ss01; sub I' zero by I.ss01; } ss03;"
        # Arabic engines run features in stages
        for scripts in ("languagesystem arab dflt;", "languagesystem latn dflt; languagesystem arab dflt;"):
            font = with_features(scripts + "feature calt { sub O' I by o; } calt;" + rules)
            self.assertEqual(freeze_features(font, "ss03").moved, [], scripts)  # also when Latin shares that calt
        # apps would pick the first alternate, not the second
        fea = ("lookup ALT { sub I from [I.ss01 H]; } ALT; feature calt { sub O' I by o; } calt;"
               "feature cv01 { sub zero from [zero.ss01 O]; sub I' lookup ALT zero; } cv01;")
        result = freeze_features(with_features(fea), "cv01=2")
        self.assertEqual((result.partial, result.moved), (["cv01"], []))
        self.assertEqual(freeze_features(with_features(fea), "cv01").moved, ["cv01"])  # the first alternate is fine
        font = with_features(fea)
        for lookup in font["GSUB"].table.LookupList.Lookup:  # large fonts wrap every lookup in an extension
            for i, subtable in enumerate(lookup.SubTable):
                lookup.SubTable[i] = extension = otTables.ExtensionSubst()
                extension.Format, extension.ExtensionLookupType, extension.ExtSubTable = 1, lookup.LookupType, subtable
            lookup.LookupType = 7
        self.assertEqual(freeze_features(font, "cv01=2").moved, [])

    def test_partial_features_are_reported(self):
        font = with_features("feature ss03 { sub zero by zero.ss01; sub I' zero by I.ss01; } ss03;")
        result = freeze_features(font, "ss03")
        self.assertEqual((result.remapped, result.partial), (1, ["ss03"]))


class DisableTest(unittest.TestCase):
    def test_disable_empties_lookups(self):
        font = fx.open_font(fx.static_ttf())
        disable_features(font, ["liga"])
        record = next(r for r in font["GSUB"].table.FeatureList.FeatureRecord if r.FeatureTag == "liga")
        self.assertEqual(record.Feature.LookupListIndex, [])
        self.assertIn("liga", list_features(font))  # the record stays, indices stay valid

    def test_disable_reaches_gpos_and_feature_variations(self):
        font = fx.open_font(fx.axis_swap_variable_ttf())
        addOpenTypeFeaturesFromString(font, "feature kern { pos H O -50; } kern;", tables=["GPOS"])
        disable_features(font, ["kern", "rvrn"])
        kern = next(r for r in font["GPOS"].table.FeatureList.FeatureRecord if r.FeatureTag == "kern")
        self.assertEqual(kern.Feature.LookupListIndex, [])
        swap = font["GSUB"].table.FeatureVariations.FeatureVariationRecord[0].FeatureTableSubstitution
        self.assertEqual(swap.SubstitutionRecord[0].Feature.LookupListIndex, [])

    def test_scripts_left_without_features_stay(self):
        # without its own entry, Latin text would get DFLT's positioning instead
        font = fx.open_font(fx.static_ttf())
        addOpenTypeFeaturesFromString(font, "languagesystem DFLT dflt; languagesystem latn dflt;"
                                            "feature kern { script latn; pos H O -50; } kern;"
                                            "feature dist { script DFLT; pos H 10; } dist;", tables=["GPOS"])
        disable_features(font, ["kern"])
        font = fx.open_font(fx._save(font))
        gpos = font["GPOS"].table
        latn = next(s.Script for s in gpos.ScriptList.ScriptRecord if s.ScriptTag == "latn")
        self.assertEqual([gpos.FeatureList.FeatureRecord[i].Feature.LookupListIndex
                          for i in latn.DefaultLangSys.FeatureIndex], [[]])

    def test_disable_unknown(self):
        with self.assertRaisesRegex(FontmintError, "no feature.*kern"):
            disable_features(fx.open_font(fx.static_ttf()), ["kern"])


if __name__ == "__main__":
    unittest.main()
