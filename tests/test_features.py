import unittest

from fontmint.common import FontmintError
from fontmint.features import freeze_features, list_features

from . import fixtures as fx


class FeaturesTest(unittest.TestCase):
    def test_list(self):
        self.assertEqual(list_features(fx.open_font(fx.static_ttf())), ["liga", "ss01"])

    def test_freeze_remaps_cmap(self):
        font = fx.open_font(fx.static_ttf())
        self.assertEqual(freeze_features(font, "ss01"), 2)
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
        self.assertEqual(freeze_features(fx.open_font(fx.static_ttf()), "liga"), 0)

    def test_spaces_and_trailing_commas(self):
        font = fx.open_font(fx.static_ttf())
        self.assertEqual(freeze_features(font, " ss01 , "), 2)
        with self.assertRaisesRegex(FontmintError, r"feature\(s\): ss02$"):
            freeze_features(font, "ss01, ss02")

    def test_missing_feature(self):
        with self.assertRaisesRegex(FontmintError, "no GSUB feature.*ss02"):
            freeze_features(fx.open_font(fx.static_ttf()), "ss01,ss02")


if __name__ == "__main__":
    unittest.main()
