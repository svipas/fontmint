import unittest

from fontmint.common import FontmintError, family_name
from fontmint.naming import (
    apply_style_name,
    check_name,
    normalize_style,
    ps_name,
    rename_family,
    set_static_names,
    style_from_location,
    weight_name,
    width_class,
    width_name,
)

from . import fixtures as fx


class StyleNameTest(unittest.TestCase):
    def test_weights(self):
        self.assertEqual(style_from_location({"wght": 400}, set(), False), "Regular")
        self.assertEqual(style_from_location({"wght": 700}, set(), False), "Bold")
        self.assertEqual(style_from_location({"wght": 375}, set(), False), "W375")
        self.assertEqual(style_from_location({}, set(), False), "Regular")

    def test_widths(self):
        self.assertEqual(style_from_location({"wght": 400, "wdth": 75}, set(), False), "Condensed")
        self.assertEqual(style_from_location({"wght": 700, "wdth": 75}, set(), False), "Condensed Bold")
        self.assertEqual(style_from_location({"wght": 400, "wdth": 100}, set(), False), "Regular")
        self.assertEqual(style_from_location({"wght": 400, "wdth": 80}, set(), False), "Wdth80")

    def test_italic_and_slant(self):
        self.assertEqual(style_from_location({"wght": 400}, set(), True), "Italic")
        self.assertEqual(style_from_location({"wght": 700}, set(), True), "Bold Italic")
        self.assertEqual(style_from_location({"wght": 400, "ital": 1}, set(), False), "Italic")
        self.assertEqual(style_from_location({"wght": 400, "slnt": -10}, set(), False), "Oblique")
        self.assertEqual(style_from_location({"wght": 700, "wdth": 75}, set(), True), "Condensed Bold Italic")

    def test_several_slants_get_labels(self):
        self.assertEqual(style_from_location({"wght": 400, "slnt": -5}, {"slnt"}, False), "Slnt-5 Oblique")
        self.assertEqual(style_from_location({"wght": 400, "slnt": 0}, {"slnt"}, False), "Slnt0")

    def test_labeled_extra_axes(self):
        self.assertEqual(style_from_location({"wght": 400, "opsz": 32}, {"opsz"}, False), "Opsz32")
        self.assertEqual(style_from_location({"wght": 700, "MONO": 1}, {"MONO"}, False), "Bold MONO1")
        # an extra axis with a single value isn't labeled
        self.assertEqual(style_from_location({"wght": 700, "opsz": 32}, set(), False), "Bold")

    def test_regular_is_dropped_next_to_other_words(self):
        self.assertEqual(normalize_style("Condensed Regular"), "Condensed")
        self.assertEqual(normalize_style("Regular Italic"), "Italic")
        self.assertEqual(normalize_style("Regular"), "Regular")

    def test_two_word_weights_and_widths_become_one(self):
        self.assertEqual(normalize_style("Extra Bold"), "ExtraBold")  # "Bold" alone would link it as the bold style
        self.assertEqual(normalize_style("Semi Condensed Extra Light Italic"), "SemiCondensed ExtraLight Italic")
        self.assertEqual(normalize_style("Ultra Italic"), "Ultra Italic")

    def test_style_name_override(self):
        self.assertEqual(apply_style_name("Regular", False), "Regular")
        self.assertEqual(apply_style_name("Regular", True), "Italic")
        self.assertEqual(apply_style_name("Book", True), "Book Italic")
        self.assertEqual(apply_style_name("Bold Italic", True), "Bold Italic")

    def test_helpers(self):
        self.assertEqual(weight_name(400), "Regular")
        self.assertEqual(weight_name(400.5), "W400.5")
        self.assertEqual(width_name(87.5), "SemiCondensed")
        self.assertEqual(width_name(100), "")
        self.assertEqual([width_class(v) for v in (50, 75, 80, 100, 125, 200)], [1, 3, 3, 5, 7, 9])


class NameValidationTest(unittest.TestCase):
    def test_valid(self):
        for name in ("Inter Clear", "JetBrains Mono 2", "Mint-Sans", "A.B"):
            check_name(name, "--name")

    def test_invalid(self):
        for name in ("Clär", "a/../../b", "Mint (Alt)", "50%", "..", " ", "Mint:Sans", 'a"b', "x|y", "back\\slash"):
            with self.subTest(name=name), self.assertRaises(FontmintError):
                check_name(name, "--name")

    def test_postscript_length(self):
        self.assertEqual(ps_name("Mint Sans", "Bold Italic"), "MintSans-BoldItalic")
        with self.assertRaisesRegex(FontmintError, "longer than 63"):
            ps_name("A" * 60, "Bold")


class RenameFamilyTest(unittest.TestCase):
    def test_identifying_names_change(self):
        font = fx.open_font(fx.static_ttf())
        rename_family(font, "Test Sans", "Mint Sans")
        name = font["name"]
        self.assertEqual(name.getDebugName(1), "Mint Sans")
        self.assertEqual(name.getDebugName(4), "Mint Sans Regular")
        self.assertEqual(name.getDebugName(6), "MintSans-Regular")
        self.assertEqual(name.getDebugName(3), "1.000;TEST;MintSans-Regular")

    def test_notices_never_change(self):
        font = fx.open_font(fx.static_ttf())
        rename_family(font, "Test Sans", "Mint Sans")
        self.assertEqual(font["name"].getDebugName(0), fx.COPYRIGHT)
        self.assertEqual(font["name"].getDebugName(7), fx.TRADEMARK)
        self.assertIn("Test Sans", font["name"].getDebugName(13))

    def test_single_word_family(self):
        """'Inter' is both the display and PostScript form - each name kind must get the right one."""
        font = fx.open_font(fx.static_ttf())
        name = font["name"]
        for i, value in (
            (1, "Inter Medium"),
            (16, "Inter"),
            (17, "Medium"),
            (4, "Inter Medium"),
            (6, "Inter-Medium"),
            (3, "1.000;TEST;Inter-Medium"),
        ):
            name.setName(value, i, 3, 1, 0x409)
        rename_family(font, "Inter", "Mint New")
        self.assertEqual(name.getDebugName(1), "Mint New Medium")
        self.assertEqual(name.getDebugName(16), "Mint New")
        self.assertEqual(name.getDebugName(6), "MintNew-Medium")
        self.assertEqual(name.getDebugName(3), "1.000;TEST;MintNew-Medium")

    def test_postscript_name_without_the_family(self):
        font = fx.open_font(fx.static_ttf())
        font["name"].setName("TestSANS-Regular", 6, 3, 1, 0x409)
        font["name"].setName("1.000;TEST;TestSANS-Regular", 3, 3, 1, 0x409)
        warnings = rename_family(font, "Test Sans", "Mint Sans")
        self.assertEqual(font["name"].getDebugName(6), "MintSans-Regular")
        self.assertEqual(font["name"].getDebugName(3), "1.000;TEST;MintSans-Regular")
        self.assertEqual(warnings, [])

    def test_postscript_name_without_hyphen_is_left_alone(self):
        font = fx.open_font(fx.static_ttf())
        font["name"].setName("TestSANSBold", 6, 3, 1, 0x409)
        warnings = rename_family(font, "Test Sans", "Mint Sans")
        self.assertEqual(font["name"].getDebugName(6), "TestSANSBold")  # no suffix to keep: don't guess
        self.assertTrue(any("PostScript name 'TestSANSBold'" in w for w in warnings))

    def test_no_leftover_warning_when_new_name_contains_old(self):
        font = fx.open_font(fx.static_ttf())
        self.assertEqual(rename_family(font, "Test Sans", "Test Sans Clear"), [])
        self.assertEqual(font["name"].getDebugName(6), "TestSansClear-Regular")

    def test_localized_family_names_are_dropped(self):
        font = fx.open_font(fx.static_ttf())
        font["name"].setName("テスト サンズ", 1, 3, 1, 0x411)
        font["name"].setName("テスト サンズ", 16, 3, 1, 0x411)
        rename_family(font, "Test Sans", "Mint Sans")
        self.assertFalse([r for r in font["name"].names if r.langID == 0x411 and r.nameID in (1, 16)])

    def test_family_without_the_style_words_in_name_id_1(self):
        # older fonts have no ID 16: ID 1 "Test Sans SemiBold" + ID 2 "Regular"
        font = fx.open_font(fx.static_ttf())
        font["name"].setName("Test Sans SemiBold", 1, 3, 1, 0x409)
        font["name"].setName("Test Sans SemiBold", 4, 3, 1, 0x409)
        font["name"].setName("TestSans-SemiBold", 6, 3, 1, 0x409)
        self.assertEqual(family_name(font), "Test Sans")
        rename_family(font, family_name(font), "Mint Sans")
        self.assertEqual(
            [font["name"].getDebugName(i) for i in (1, 4, 6)],
            ["Mint Sans SemiBold", "Mint Sans SemiBold", "MintSans-SemiBold"],
        )

    def test_fonts_without_windows_names(self):
        font = fx.open_font(fx.static_ttf())
        for record in font["name"].names:
            record.string = record.toUnicode()
            record.platformID, record.platEncID, record.langID = 0, 3, 0
        self.assertEqual(family_name(font), "Test Sans")
        rename_family(font, "Test Sans", "Mint Sans")
        self.assertEqual(
            [font["name"].getDebugName(i) for i in (0, 1, 6)], [fx.COPYRIGHT, "Mint Sans", "MintSans-Regular"]
        )

    def test_font_without_a_family_name_cannot_be_renamed(self):
        font = fx.open_font(fx.static_ttf())
        font["name"].setName("", 1, 3, 1, 0x409)
        self.assertEqual(family_name(font), "Font")
        with self.assertRaisesRegex(FontmintError, "doesn't state its family name"):
            rename_family(font, family_name(font), "Mint Sans")

    def test_undecodable_records_are_left_alone(self):
        font = fx.open_font(fx.static_ttf())
        full_name = font["name"].getName(4, 3, 1, 0x409)
        full_name.string = b"\x00T\x00e\x00"  # odd length: not UTF-16
        rename_family(font, "Test Sans", "Mint Sans")
        self.assertEqual(full_name.string, b"\x00T\x00e\x00")
        self.assertEqual(font["name"].getDebugName(1), "Mint Sans")

    def test_english_family_wins(self):
        font = fx.open_font(fx.static_ttf())
        font["name"].setName("テスト サンズ", 16, 3, 1, 0x411)  # only a Japanese typographic family
        self.assertEqual(family_name(font), "Test Sans")

    def test_leftover_names_warn(self):
        font = fx.open_font(fx.static_ttf())
        font["name"].setName("TestSans Regular", 4, 3, 1, 0x409)  # PostScript-style family inside a display name
        warnings = rename_family(font, "Test Sans", "Mint")
        self.assertTrue(warnings and "still contain" in warnings[0])

    def test_cff_names_follow(self):
        font = fx.open_font(fx.static_otf())
        rename_family(font, "Test Sans", "Mint Sans")
        cff = font["CFF "].cff
        self.assertEqual(cff.fontNames, ["MintSans-Regular"])
        self.assertEqual(cff.topDictIndex[0].FamilyName, "Mint Sans")
        self.assertEqual(cff.topDictIndex[0].FullName, "Mint Sans Regular")

    def test_variable_instance_names(self):
        font = fx.open_font(fx.variable_ttf())
        rename_family(font, "Test Sans", "Mint Sans")
        names = {r.toUnicode() for r in font["name"].names if r.nameID >= 256}
        self.assertIn("Condensed Bold", names)  # instance styles untouched
        self.assertEqual(font["name"].getDebugName(6), "MintSans-Regular")


class SetStaticNamesTest(unittest.TestCase):
    def names(self, style, weight=400, width=None):
        font = fx.open_font(fx.static_ttf())
        ps = set_static_names(font, "Mint Sans", style, weight, width)
        n = font["name"]
        return ps, font, {i: n.getDebugName(i) for i in (1, 2, 4, 6, 16, 17)}

    def test_ribbi(self):
        ps, font, n = self.names("Bold Italic", 700)
        self.assertEqual(ps, "MintSans-BoldItalic")
        self.assertEqual((n[1], n[2], n[16], n[17]), ("Mint Sans", "Bold Italic", None, None))
        self.assertEqual(font["OS/2"].fsSelection & 0b100001, 0b100001)  # italic + bold bits
        self.assertEqual(font["head"].macStyle, 3)

    def test_bold_links_within_its_width(self):
        ps, font, n = self.names("Condensed Bold", 700, 3)
        self.assertEqual(ps, "MintSans-CondensedBold")
        self.assertEqual((n[1], n[2], n[16], n[17]), ("Mint Sans Condensed", "Bold", "Mint Sans", "Condensed Bold"))
        self.assertEqual((font["OS/2"].usWidthClass, font["OS/2"].usWeightClass), (3, 700))
        self.assertTrue(font["OS/2"].fsSelection & (1 << 5))  # bold bit, so Ctrl+B in "Condensed" finds it

    def test_non_linked_weight(self):
        _, font, n = self.names("SemiBold Italic", 600)
        self.assertEqual((n[1], n[2], n[16], n[17]), ("Mint Sans SemiBold", "Italic", "Mint Sans", "SemiBold Italic"))
        self.assertFalse(font["OS/2"].fsSelection & (1 << 5))

    def test_custom_weight_keeps_real_weight_class(self):
        _, font, n = self.names("Regular", 375)
        self.assertEqual(n[2], "Regular")
        self.assertEqual(font["OS/2"].usWeightClass, 375)
        self.assertTrue(font["OS/2"].fsSelection & (1 << 6))  # REGULAR bit

    def test_notices_stay_and_stale_names_go_on_every_platform(self):
        font = fx.open_font(fx.static_ttf())
        font["name"].setName("Standard", 2, 3, 1, 0x407)  # German "Regular"
        set_static_names(font, "Mint Sans", "Bold", 700)
        records = {(r.nameID, r.platformID, r.langID): r.toUnicode() for r in font["name"].names}
        self.assertEqual(
            {key: value for key, value in records.items() if key[0] in (1, 2)},
            {(1, 3, 0x409): "Mint Sans", (2, 3, 0x409): "Bold"},
        )
        self.assertEqual({platform for _, platform, _ in records}, {3})

        font = fx.open_font(fx.static_ttf())  # a font with Mac names only keeps its notices
        font["name"].names = [r for r in font["name"].names if r.platformID != 3]
        font["name"].setName(fx.COPYRIGHT, 0, 1, 0, 0)
        font["name"].setName("Test Sans", 1, 1, 0, 0)
        set_static_names(font, "Mint Sans", "Bold", 700)
        records = {(r.nameID, r.platformID, r.langID): r.toUnicode() for r in font["name"].names}
        self.assertEqual((records[(0, 1, 0)], records[(1, 3, 0x409)]), (fx.COPYRIGHT, "Mint Sans"))
        self.assertNotIn((1, 1, 0), records)

    def test_oblique(self):
        _, font, n = self.names("Oblique")
        self.assertEqual((n[1], n[2], n[16], n[17]), ("Mint Sans", "Italic", "Mint Sans", "Oblique"))
        self.assertTrue(font["OS/2"].fsSelection & (1 << 9))  # OBLIQUE bit


if __name__ == "__main__":
    unittest.main()
