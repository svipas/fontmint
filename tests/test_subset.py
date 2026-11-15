import unittest

from fontTools.ttLib import newTable

from fontmint import FontmintError, Options, mint, prepare
from fontmint.subset import parse_subset, subset_font

from . import fixtures as fx


class ParseTest(unittest.TestCase):
    def test_presets_and_ranges(self):
        self.assertEqual(parse_subset("U+0030, u+0041-0043,"), {0x30, 0x41, 0x42, 0x43})
        latin = parse_subset("latin")
        self.assertTrue({ord("A"), ord("é"), ord("€")} <= latin)
        self.assertNotIn(ord("ł"), latin)
        self.assertIn(ord("ł"), parse_subset("Latin,latin-ext"))

    def test_errors(self):
        for bad in ("klingon", "U+0043-0041", "U+110000", "0041"):
            with self.subTest(spec=bad), self.assertRaises(FontmintError):
                parse_subset(bad)


class SubsetTest(unittest.TestCase):
    def test_keeps_characters_features_and_names(self):
        font = fx.open_font(fx.static_ttf())
        names = sorted({(n.nameID, n.platformID, n.langID) for n in font["name"].names})
        self.assertEqual(subset_font(font, parse_subset("U+0030,U+0049")), (2, 8, []))
        self.assertEqual(set(font.getBestCmap()), {0x30, 0x49})
        self.assertIn("zero.ss01", font.getGlyphOrder())  # reachable through ss01
        self.assertNotIn("x", font.getGlyphOrder())
        self.assertEqual(sorted({(n.nameID, n.platformID, n.langID) for n in font["name"].names}), names)
        self.assertIn("ss01", {r.FeatureTag for r in font["GSUB"].table.FeatureList.FeatureRecord})

    def test_dropped_tables_are_reported_not_logged(self):
        font = fx.open_font(fx.static_ttf())
        font["Xtra"] = newTable("Xtra")  # a table fontTools doesn't know, so it can't subset it
        font["Xtra"].data = b"\0" * 4
        with self.assertNoLogs(level="WARNING"):  # nothing reaches the terminal
            prepared = prepare(fx._save(font), Options(name="Mint Sans", subset="U+0030"))
        self.assertTrue(any("dropped the tables Xtra" in w for w in prepared.warnings), prepared.warnings)
        self.assertEqual(prepared.subset, (1, 8))

    def test_nothing_left(self):
        with self.assertRaisesRegex(FontmintError, "none of the characters"):
            subset_font(fx.open_font(fx.static_ttf()), parse_subset("cyrillic"))

    def test_static_and_variable_outputs(self):
        static = mint(fx.static_woff2(), Options(name="Mint Sans", subset="U+0030,U+0049"))
        variable = mint(fx.variable_ttf(), Options(name="Mint Sans", subset="U+0030,U+0049", hint=False))
        for files in (static, variable):
            for path, out in files.items():
                with self.subTest(path=path):
                    self.assertEqual(set(fx.open_font(out).getBestCmap()), {0x30, 0x49})
        with self.assertRaisesRegex(FontmintError, "isn't a subset"):
            mint(fx.static_ttf(), Options(subset="emoji"))


if __name__ == "__main__":
    unittest.main()
