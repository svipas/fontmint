import unittest

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

from fontmint.common import FontmintError
from fontmint.features import disable_features, freeze_features, list_features, parse_features

from . import fixtures as fx


class FeaturesTest(unittest.TestCase):
    def test_list(self):
        self.assertEqual(list_features(fx.open_font(fx.static_ttf())), ["liga", "ss01"])

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

    def test_ligatures_cannot_be_frozen(self):
        self.assertEqual(freeze_features(fx.open_font(fx.static_ttf()), "liga").remapped, 0)

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
        for number, expected in ((1, "zero.ss01"), (2, "O"), (3, "o"), (4, "zero")):
            with self.subTest(number=number):
                font = with_features(fea)
                freeze_features(font, f"cv01={number}")
                self.assertEqual(font.getBestCmap()[ord("0")], expected)

    def test_script_without_default_language_system(self):
        font = fx.open_font(fx.static_ttf())
        for record in font["GSUB"].table.ScriptList.ScriptRecord:
            record.Script.DefaultLangSys = None
        self.assertEqual(freeze_features(font, "ss01").remapped, 2)

    def test_old_mac_cmap_is_left_alone_for_high_glyph_ids(self):
        font = fx.open_font(fx.mac_cmap_ttf())
        freeze_features(font, "ss01")
        mac = next(t for t in font["cmap"].tables if t.format == 0)
        self.assertEqual(mac.cmap[ord("0")], "zero")  # zero.ss01 doesn't fit in a format 0 subtable
        self.assertEqual(font.getBestCmap()[ord("0")], "zero.ss01")
        fx._save(font)  # used to fail with OverflowError


class FreezeRepairTest(unittest.TestCase):
    def test_ligatures_follow_frozen_glyphs(self):
        font = fx.open_font(fx.static_ttf())
        freeze_features(font, "ss01")
        lookup = next(lk for lk in font["GSUB"].table.LookupList.Lookup if lk.LookupType == 4)
        ligatures = lookup.SubTable[0].ligatures
        self.assertEqual([(lig.Component, lig.LigGlyph) for lig in ligatures["I.ss01"]], [(["zero.ss01"], "H")])
        self.assertIn("I", ligatures)  # the original ligature stays

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

    def test_disable_unknown(self):
        with self.assertRaisesRegex(FontmintError, "no feature.*kern"):
            disable_features(fx.open_font(fx.static_ttf()), ["kern"])


if __name__ == "__main__":
    unittest.main()
