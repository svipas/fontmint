import unittest

from fontTools.cffLib import SubrsIndex
from fontTools.misc.psCharStrings import T2CharString, T2WidthExtractor
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import newTable
from fontTools.ttLib.tables import otTables

from fontmint import FontmintError, Options, inspect, mint
from fontmint.metrics import add_letter_spacing, line_height, set_line_height

from . import fixtures as fx


class LineHeightTest(unittest.TestCase):
    def test_extra_space_is_split_above_and_below(self):
        font = fx.open_font(fx.static_ttf())  # ascent 800, descent -200, 1000 units per em
        self.assertEqual(line_height(font), 1.0)
        set_line_height(font, 1.25)
        self.assertEqual((font["hhea"].ascent, font["hhea"].descent, font["hhea"].lineGap), (925, -325, 0))
        os2 = font["OS/2"]
        self.assertEqual((os2.sTypoAscender, os2.sTypoDescender, os2.sTypoLineGap), (925, -325, 0))
        self.assertEqual((os2.usWinAscent, os2.usWinDescent), (925, 325))
        self.assertTrue(os2.fsSelection & (1 << 7))  # apps are told to use the typo values

    def test_windows_clipping_area_never_shrinks(self):
        font = fx.open_font(fx.static_ttf())
        set_line_height(font, 0.8)
        self.assertEqual((font["hhea"].ascent, font["hhea"].descent), (700, -100))
        self.assertEqual((font["OS/2"].usWinAscent, font["OS/2"].usWinDescent), (800, 200))

    def test_line_metric_variations_are_dropped(self):
        font = fx.open_font(fx.variable_ttf())
        font["MVAR"] = newTable("MVAR")
        font["MVAR"].table = mvar = otTables.MVAR()
        mvar.ValueRecord = []
        for tag in ("hasc", "xhgt"):
            record = otTables.MetricsValueRecord()
            record.ValueTag, record.VarIdx = tag, 0
            mvar.ValueRecord.append(record)
        font["VDMX"] = newTable("VDMX")  # line metrics per pixel size
        set_line_height(font, 1.5)
        self.assertEqual([r.ValueTag for r in font["MVAR"].table.ValueRecord], ["xhgt"])
        self.assertNotIn("VDMX", font)


class LetterSpacingTest(unittest.TestCase):
    def test_space_is_added_after_every_glyph_with_a_width(self):
        font = fx.open_font(fx.static_ttf())
        font["hmtx"].metrics["O"] = (0, 0)  # stands in for a combining accent
        before = dict(font["hmtx"].metrics)
        add_letter_spacing(font, 0.05)
        for name, (advance, lsb) in font["hmtx"].metrics.items():
            self.assertEqual((advance, lsb), (before[name][0] + 50 if before[name][0] else 0, before[name][1]))
        self.assertEqual(font["hhea"].advanceWidthMax, max(a for a, _ in font["hmtx"].metrics.values()))

    def cff_widths(self, font) -> dict:
        top = font["CFF "].cff.topDictIndex[0]
        widths = {}
        for name in top.CharStrings.keys():
            charstring = top.CharStrings[name]
            private = charstring.private
            extractor = T2WidthExtractor(getattr(private, "Subrs", []), top.GlobalSubrs, private.nominalWidthX,
                                         private.defaultWidthX)
            extractor.execute(charstring)
            widths[name] = extractor.width
        return widths

    def outlines(self, font) -> dict:
        glyphs, drawn = font.getGlyphSet(), {}
        for name in font.getGlyphOrder():
            drawn[name] = RecordingPen()
            glyphs[name].draw(drawn[name])
        return {name: pen.value for name, pen in drawn.items()}

    def test_cff_outlines_store_the_same_width(self):
        font = fx.open_font(fx.static_otf())
        add_letter_spacing(font, 0.05)
        font = fx.open_font(fx._save(font))
        self.assertEqual(self.cff_widths(font), {name: 650 for name in font.getGlyphOrder()})

    def test_cff_widths_left_to_the_default_or_kept_in_a_subroutine(self):
        # real OTFs leave out the width of glyphs that have the font's default width (an
        # empty glyph is then just "endchar"), and a subroutine can hold the width
        font = fx.open_font(fx.static_otf())
        top = font["CFF "].cff.topDictIndex[0]
        top.Private.defaultWidthX = fx.ADVANCE
        for name in ("space", "H"):
            top.CharStrings[name].decompile()
            del top.CharStrings[name].program[0]
        shared = top.CharStrings["O"]
        shared.decompile()
        subroutine = T2CharString(program=[*shared.program[:4], "return"])  # width, x, y, rmoveto
        top.Private.Subrs = SubrsIndex()
        top.Private.Subrs.append(subroutine)
        shared.program[:4] = [-107, "callsubr"]  # -107 is subroutine 0
        font = fx.open_font(fx._save(font))
        before = self.outlines(font)

        add_letter_spacing(font, 0.05)
        font = fx.open_font(fx._save(font))
        self.assertEqual(self.cff_widths(font), {name: 650 for name in font.getGlyphOrder()})
        self.assertEqual(self.outlines(font), before)

    def test_double_width_glyphs_of_a_monospaced_font_get_twice_the_space(self):
        font = fx.open_font(fx.static_ttf())
        font["hmtx"].metrics["H"] = (1200, 60)  # fills two cells
        add_letter_spacing(font, 0.05)
        self.assertEqual((font["hmtx"]["H"][0], font["hmtx"]["O"][0]), (1300, 650))
        font["hmtx"].metrics["x"] = (500, 30)  # proportional now: everything gets the same space
        add_letter_spacing(font, 0.05)
        self.assertEqual((font["hmtx"]["H"][0], font["hmtx"]["O"][0]), (1350, 700))

    def test_negative_spacing_never_goes_below_zero(self):
        font = fx.open_font(fx.static_ttf())
        add_letter_spacing(font, -0.5)
        self.assertTrue(all(advance >= 0 for advance, _ in font["hmtx"].metrics.values()))


class MetricsOptionsTest(unittest.TestCase):
    def test_static_and_variable_outputs(self):
        static = mint(fx.static_otf(), Options(name="Mint Sans", line_height=1.5, letter_spacing=0.02))
        plain = mint(fx.variable_ttf(), Options(name="Mint Sans", axes={"wght": "700"}, formats="ttf", hint=False))
        spaced = mint(fx.variable_ttf(), Options(name="Mint Sans", line_height=1.5, letter_spacing=0.02,
                                                 axes={"wght": "700"}, formats="ttf", hint=False))
        for path, data in {**static, **spaced}.items():
            with self.subTest(path=path):
                self.assertAlmostEqual(inspect(data).line_height, 1.5)
        (path, data), = spaced.items()
        before, after = fx.open_font(plain[path])["hmtx"], fx.open_font(data)["hmtx"]
        self.assertEqual(after["H"][0], before["H"][0] + 20)  # on top of the bold instance's own width

    def test_spacing_is_decided_per_instance(self):
        # like Recursive's fraction slash: no width at the default, a full one in the condensed style
        source = fx.open_font(fx.variable_ttf())
        source["hmtx"].metrics["x"] = (0, 30)
        for variation in source["gvar"].variations["x"]:
            if "wdth" in variation.axes:
                variation.coordinates[5] = (600, 0)  # the advance width's point: 0 → 600 at wdth 75
        options = Options(name="Mint Sans", letter_spacing=0.05, formats="ttf", hint=False)
        files = mint(fx._save(source), options)
        widths = {path.split("/")[-1]: fx.open_font(data)["hmtx"]["x"][0] for path, data in files.items()}
        self.assertEqual(widths["MintSans[wght,wdth].ttf"], 0)  # the variable font decides at its default
        self.assertEqual((widths["MintSans-Regular.ttf"], widths["MintSans-Condensed.ttf"]), (0, 650))

    def test_out_of_range(self):
        for options, message in ((Options(line_height=0), "--line-height 0 is out of range"),
                                 (Options(letter_spacing=2), "--letter-spacing 2 is out of range")):
            with self.subTest(message=message), self.assertRaisesRegex(FontmintError, message):
                mint(fx.static_ttf(), options)


if __name__ == "__main__":
    unittest.main()
