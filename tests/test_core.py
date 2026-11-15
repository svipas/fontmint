import io
import subprocess
import sys
import unittest
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.misc.xmlWriter import XMLWriter

from fontmint import FontmintError, Options, inspect, mint, prepare

from . import fixtures as fx

ROOT = Path(__file__).resolve().parent.parent


def table_xml(font, tag: str) -> str:
    buf = io.StringIO()
    font[tag].toXML(XMLWriter(buf), font)
    return buf.getvalue()


def rvrn_result(font, glyph: str) -> str:
    """What a static font's always-on rvrn feature turns `glyph` into."""
    gsub = font["GSUB"].table
    for record in gsub.FeatureList.FeatureRecord:
        if record.FeatureTag == "rvrn":
            for index in record.Feature.LookupListIndex:
                glyph = gsub.LookupList.Lookup[index].SubTable[0].mapping.get(glyph, glyph)
    return glyph


def folders(files: dict) -> set[str]:
    return {path.split("/")[1] for path in files}


class StaticInputTest(unittest.TestCase):
    """Static fonts pass through: freeze + rename only, same format, nothing else."""

    def test_ttf_passthrough(self):
        files = mint(fx.static_ttf(), Options(features="ss01", name="Mint Sans"))
        self.assertEqual(list(files), ["MintSans/MintSans-Regular.ttf"])
        src, out = fx.open_font(fx.static_ttf()), fx.open_font(files["MintSans/MintSans-Regular.ttf"])

        self.assertIsNone(out.flavor)
        self.assertNotIn("CFF ", out)
        self.assertEqual(out.getBestCmap()[ord("0")], "zero.ss01")
        for tag in ("fpgm", "prep", "cvt "):  # hinting kept byte for byte
            self.assertEqual(src.getTableData(tag), out.getTableData(tag), tag)
        for g in src.getGlyphOrder():  # outlines + instructions untouched
            self.assertEqual(src["glyf"][g].compile(src["glyf"]), out["glyf"][g].compile(out["glyf"]), g)
        changed = {t for t in src.keys() if t != "GlyphOrder" and src.getTableData(t) != out.getTableData(t)}
        self.assertLessEqual(changed, {"cmap", "name", "head", "GSUB"})
        # liga runs after ss01 here, so no rule needs updating: GSUB content is unchanged
        self.assertEqual(table_xml(src, "GSUB"), table_xml(out, "GSUB"))
        self.assertEqual(out["name"].getDebugName(0), fx.COPYRIGHT)

    def test_otf_passthrough(self):
        files = mint(fx.static_otf(), Options(features="ss01", name="Mint Sans"))
        self.assertEqual(list(files), ["MintSans/MintSans-Regular.otf"])
        src, out = fx.open_font(fx.static_otf()), fx.open_font(files["MintSans/MintSans-Regular.otf"])
        self.assertEqual(out.sfntVersion, "OTTO")
        self.assertEqual(out.getBestCmap()[ord("I")], "I.ss01")
        cs_src = src["CFF "].cff.topDictIndex[0].CharStrings
        cs_out = out["CFF "].cff.topDictIndex[0].CharStrings
        for g in src.getGlyphOrder():
            cs_src[g].decompile(); cs_out[g].decompile()
            self.assertEqual(cs_src[g].program, cs_out[g].program, g)
        self.assertEqual(out["CFF "].cff.fontNames, ["MintSans-Regular"])

    def test_woff2_stays_woff2(self):
        files = mint(fx.static_woff2(), Options(features="ss01", name="Mint Sans"))
        self.assertEqual(list(files), ["MintSans/MintSans-Regular.woff2"])
        self.assertEqual(fx.open_font(files["MintSans/MintSans-Regular.woff2"]).flavor, "woff2")

    def test_rename_only(self):
        files = mint(fx.static_ttf(), Options(name="Mint Sans"))
        out = fx.open_font(files["MintSans/MintSans-Regular.ttf"])
        self.assertEqual(out.getBestCmap()[ord("0")], "zero")

    def test_axis_options_rejected(self):
        with self.assertRaisesRegex(FontmintError, "only apply to variable fonts"):
            mint(fx.static_ttf(), Options(axes={"wght": "400"}))
        with self.assertRaisesRegex(FontmintError, "style-name"):
            mint(fx.static_ttf(), Options(style_name="Regular"))

    def test_formats_ignored_with_warning(self):
        p = prepare(fx.static_ttf(), Options(name="Mint Sans", formats={"woff2"}))
        self.assertEqual(list(p.files), ["MintSans/MintSans-Regular.ttf"])
        self.assertTrue(any("formats are ignored" in w for w in p.warnings))

    def test_freeze_without_name_warns(self):
        p = prepare(fx.static_ttf(), Options(features="ss01"))
        self.assertTrue(any("no --name given" in w for w in p.warnings))
        self.assertEqual(list(p.files), ["TestSans/TestSans-Regular.ttf"])


class VariableDefaultTest(unittest.TestCase):
    """No axis options: variable font + every named instance in every format."""

    @classmethod
    def setUpClass(cls):
        cls.files = mint(fx.variable_ttf(), Options(features="ss01", name="Mint Sans"))

    def test_layout(self):
        self.assertEqual(folders(self.files),
                         {"variable", "ttf-unhinted", "ttf-hinted", "otf", "woff2-unhinted", "woff2-hinted"})
        styles = sorted(p.split("/")[-1] for p in self.files if "/otf/" in p)
        self.assertEqual(styles, ["MintSans-Bold.otf", "MintSans-Condensed.otf",
                                  "MintSans-CondensedBold.otf", "MintSans-Regular.otf"])
        self.assertEqual(len(self.files), 2 + 4 * 5)

    def test_variable_output_is_only_frozen_and_renamed(self):
        vf = fx.open_font(self.files["MintSans/variable/MintSans[wght,wdth].ttf"])
        self.assertIn("fvar", vf)
        self.assertNotIn("fpgm", vf)  # never hinted
        self.assertIn("glyf", vf)     # never converted
        self.assertEqual(vf.getBestCmap()[ord("0")], "zero.ss01")
        self.assertEqual(vf["name"].getDebugName(1), "Mint Sans")
        self.assertEqual(vf["name"].getDebugName(0), fx.COPYRIGHT)
        self.assertEqual(fx.open_font(self.files["MintSans/variable/MintSans[wght,wdth].woff2"]).flavor, "woff2")

    def test_hinting_only_in_hinted_folders(self):
        for path, data in self.files.items():
            font = fx.open_font(data)
            self.assertEqual("fpgm" in font, "-hinted/" in path, path)

    def test_static_outputs(self):
        for path, data in self.files.items():
            font = fx.open_font(data)
            with self.subTest(path=path):
                self.assertEqual(font.getBestCmap()[ord("0")], "zero.ss01")
                self.assertEqual(font["name"].getDebugName(0), fx.COPYRIGHT)
                if "/variable/" not in path:
                    self.assertNotIn("fvar", font)
                if "/otf/" in path:
                    self.assertIn("CFF ", font)
                    self.assertNotIn("glyf", font)

    def test_instance_metadata(self):
        bold = fx.open_font(self.files["MintSans/ttf-unhinted/MintSans-CondensedBold.ttf"])
        self.assertEqual(bold["OS/2"].usWeightClass, 700)
        self.assertEqual(bold["OS/2"].usWidthClass, 3)
        self.assertEqual(bold["name"].getDebugName(17), "Condensed Bold")
        # instancing really moved the outlines: wght 700 is 60% of the way to 900,
        # so +80 × 0.6 = +48; condensed is −100 → 600 + 48 − 100
        self.assertEqual(bold["hmtx"]["H"][0], 548)


class HintedVariableSourceTest(unittest.TestCase):
    """A variable font with its own hinting: -hinted keeps it, -unhinted has none."""

    @classmethod
    def setUpClass(cls):
        options = Options(name="Mint Sans", axes={"wght": "700"}, formats="ttf,woff2")
        cls.files = mint(fx.variable_ttf(hinted=True), options)

    def test_unhinted_outputs_have_no_hinting(self):
        for folder, ext in (("ttf-unhinted", "ttf"), ("woff2-unhinted", "woff2")):
            font = fx.open_font(self.files[f"MintSans/{folder}/MintSans-Bold.{ext}"])
            self.assertFalse(any(t in font for t in ("fpgm", "prep", "cvt ", "gasp")), folder)
            self.assertFalse(any(font["glyf"][g].program.getBytecode() for g in font.getGlyphOrder()
                                 if hasattr(font["glyf"][g], "program")), folder)

    def test_hinted_outputs_keep_the_designers_hinting(self):
        font = fx.open_font(self.files["MintSans/ttf-hinted/MintSans-Bold.ttf"])
        for tag, data in fx.HINTING_TABLES.items():
            self.assertEqual(font.getTableData(tag), data, tag)
        self.assertNotIn("ttfautohint", font["name"].getDebugName(5) or "")


class ScanControlOnlySourceTest(unittest.TestCase):
    """A variable font with only build-tool scan control (prep + gasp) is unhinted:
    -hinted must come from ttfautohint, -unhinted must be clean."""

    def test_autohinted(self):
        files = mint(fx.variable_ttf(scan_control=True), Options(name="Mint Sans", axes={"wght": "400"}, formats="ttf"))
        hinted = fx.open_font(files["MintSans/ttf-hinted/MintSans-Regular.ttf"])
        unhinted = fx.open_font(files["MintSans/ttf-unhinted/MintSans-Regular.ttf"])
        self.assertIn("fpgm", hinted)
        self.assertIn("ttfautohint", hinted["name"].getDebugName(5))
        self.assertFalse(any(t in unhinted for t in ("prep", "gasp", "fpgm")))


class UntrustedNamesTest(unittest.TestCase):
    """Names read from a font decide folders and file names; they must never escape."""

    def evil_font(self, variable: bool) -> bytes:
        font = fx.open_font(fx.variable_ttf() if variable else fx.static_ttf())
        for name_id, value in ((1, "../../escaped"), (16, "../../escaped"), (6, "../../escaped-Regular")):
            font["name"].setName(value, name_id, 3, 1, 0x409)
        return fx._save(font)

    def test_paths_stay_inside(self):
        for variable in (False, True):
            files = mint(self.evil_font(variable), Options(axes={"wght": "400"} if variable else {}, formats="ttf",
                                                             hint=False))
            for path in files:
                with self.subTest(path=path):
                    self.assertNotIn("..", path.split("/"))
                    self.assertFalse(path.startswith("/"))
                    self.assertNotIn("\\", path)

    def test_long_postscript_names_rejected(self):
        with self.assertRaisesRegex(FontmintError, "longer than 63"):
            mint(fx.static_ttf(), Options(name="A" * 70))
        with self.assertRaisesRegex(FontmintError, "longer than 63"):
            mint(fx.variable_ttf(), Options(name="B" * 60, axes={"wght": "300:700"}))


class CorruptFontTest(unittest.TestCase):
    def test_truncated_and_empty(self):
        truncated = fx.variable_ttf()[:1500]
        header_only = b"\x00\x01\x00\x00" + b"\x00" * 8
        for data in (truncated, header_only):
            for call in (lambda d: inspect(d), lambda d: mint(d, Options(name="X"))):
                with self.subTest(size=len(data)), self.assertRaises(FontmintError):
                    call(data)


class NewOptionsTest(unittest.TestCase):
    def test_disable(self):
        files = mint(fx.static_ttf(), Options(name="Mint Sans", disable="liga"))
        out = fx.open_font(files["MintSans/MintSans-Regular.ttf"])
        record = next(r for r in out["GSUB"].table.FeatureList.FeatureRecord if r.FeatureTag == "liga")
        self.assertEqual(record.Feature.LookupListIndex, [])

    def test_language_needs_features(self):
        with self.assertRaisesRegex(FontmintError, "add the feature, e.g. --features locl"):
            mint(fx.static_ttf(), Options(name="X", language="rom"))
        with self.assertRaisesRegex(FontmintError, "no forms for language 'ROM'"):  # tag upper-cased
            mint(fx.static_ttf(), Options(name="X", features="ss01", language=" rom "))

    def test_freeze_and_disable_same_feature(self):
        with self.assertRaisesRegex(FontmintError, "can't be frozen and disabled"):
            mint(fx.static_ttf(), Options(name="X", features="ss01", disable="ss01"))

    def test_axis_dependent_swaps_survive(self):
        # at wght 900 the font shows O for '0' (rvrn runs first); with ss01 on, a text engine still shows O there
        variable = mint(fx.axis_swap_variable_ttf(), Options(name="Mint Sans", features="ss01", formats="ttf", hint=False))
        vf = fx.open_font(variable["MintSans/variable/MintSans[wght,wdth].ttf"])
        gsub = vf["GSUB"].table
        swap = gsub.FeatureVariations.FeatureVariationRecord[0].FeatureTableSubstitution.SubstitutionRecord[0]
        mapping = gsub.LookupList.Lookup[swap.Feature.LookupListIndex[0]].SubTable[0].mapping
        self.assertEqual(mapping.get("zero.ss01"), "O")  # the variable font knows the frozen glyph swaps too
        options = Options(name="Mint Sans", features="ss01", axes={"wght": "400,900"}, formats="ttf", hint=False)
        files = mint(fx.axis_swap_variable_ttf(), options)
        black = fx.open_font(files["MintSans/ttf-unhinted/MintSans-Black.ttf"])
        regular = fx.open_font(files["MintSans/ttf-unhinted/MintSans-Regular.ttf"])
        self.assertEqual(rvrn_result(black, "zero.ss01"), "O")  # always-on rvrn turns the frozen '0' into O
        self.assertEqual(rvrn_result(regular, "zero.ss01"), "zero.ss01")

    def test_monospace_flag(self):
        files = mint(fx.variable_ttf(), Options(name="Mint Sans", axes={"wght": "400,700"}, formats="ttf", hint=False))
        regular = fx.open_font(files["MintSans/ttf-unhinted/MintSans-Regular.ttf"])  # every glyph is 600 wide
        bold = fx.open_font(files["MintSans/ttf-unhinted/MintSans-Bold.ttf"])  # space stays 600, letters grow
        self.assertEqual((regular["post"].isFixedPitch, bold["post"].isFixedPitch), (1, 0))

    def test_long_family_name_warns(self):
        p = prepare(fx.variable_ttf(), Options(name="A Rather Long Family Name", axes={"wght": "700", "wdth": "75"}))
        self.assertTrue(any("longer than 31 characters" in w for w in p.warnings))

    def test_unfreezable_and_partial_warnings(self):
        p = prepare(fx.variable_ttf(), Options(name="Mint Sans", features="liga"))
        self.assertTrue(any("changed nothing" in w for w in p.warnings))
        font = fx.open_font(fx.static_ttf())
        del font["GSUB"]
        addOpenTypeFeaturesFromString(font, "feature ss03 { sub zero by zero.ss01; sub I' zero by I.ss01; } ss03;")
        p = prepare(fx._save(font), Options(name="Mint Sans", features="ss03"))
        self.assertTrue(any("ss03: only the one-to-one swaps were frozen" in w for w in p.warnings))

    def test_disabling_text_features_warns(self):
        p = prepare(fx.static_ttf(), Options(name="Mint Sans", disable="liga"))
        self.assertFalse(any("can break text" in w for w in p.warnings))
        font = fx.open_font(fx.static_ttf())
        addOpenTypeFeaturesFromString(font, "feature ccmp { sub O by o; } ccmp;")
        p = prepare(fx._save(font), Options(name="Mint Sans", disable="ccmp"))
        self.assertTrue(any("turning off ccmp can break text" in w for w in p.warnings))

    def test_long_name_warning_for_static_input_only_when_long(self):
        long = prepare(fx.static_ttf(), Options(name="A Rather Long Family Name Indeed"))
        short = prepare(fx.static_ttf(), Options(name="Mint Sans"))
        self.assertTrue(any("longer than 31 characters" in w for w in long.warnings))
        self.assertFalse(any("longer than 31 characters" in w for w in short.warnings))

    def test_monospace_flag_is_never_cleared(self):
        font = fx.open_font(fx.variable_ttf())
        font["post"].isFixedPitch = 1  # the designer says monospaced; Bold isn't, by the width check
        font["OS/2"].panose.bFamilyType = 2
        files = mint(fx._save(font), Options(name="Mint Sans", axes={"wght": "400,700"}, formats="ttf", hint=False))
        bold = fx.open_font(files["MintSans/ttf-unhinted/MintSans-Bold.ttf"])
        regular = fx.open_font(files["MintSans/ttf-unhinted/MintSans-Regular.ttf"])
        self.assertEqual(bold["post"].isFixedPitch, 1)
        self.assertEqual(regular["OS/2"].panose.bProportion, 9)


class AutohintFailureTest(unittest.TestCase):
    def test_unhintable_font_raises_fontmint_error(self):
        with self.assertRaisesRegex(FontmintError, "ttfautohint can't hint this font.*--no-hint"):
            mint(fx.symbol_variable_ttf(), Options(name="Sym", axes={"wght": "400"}, formats="ttf"))

    def test_no_hint_builds_it(self):
        files = mint(fx.symbol_variable_ttf(), Options(name="Sym", axes={"wght": "400"}, formats="ttf", hint=False))
        self.assertEqual(list(files), ["Sym/ttf-unhinted/Sym-Regular.ttf"])


class VariableItalicTest(unittest.TestCase):
    def test_italic_names(self):
        files = mint(fx.variable_ttf(italic=True), Options(name="Mint Sans", formats={"ttf"}, hint=False))
        self.assertEqual(sorted(p.split("/")[-1] for p in files), [
            "MintSans-BoldItalic.ttf", "MintSans-CondensedBoldItalic.ttf", "MintSans-CondensedItalic.ttf",
            "MintSans-Italic.ttf", "MintSans-Italic[wght,wdth].ttf",
        ])
        italic = fx.open_font(files["MintSans/ttf-unhinted/MintSans-Italic.ttf"])
        self.assertEqual(italic["name"].getDebugName(2), "Italic")
        self.assertTrue(italic["OS/2"].fsSelection & 1)

    def test_otf_keeps_italic_angle(self):
        files = mint(fx.variable_ttf(italic=True), Options(name="Mint Sans", axes={"wght": "700"}, formats="otf"))
        otf = fx.open_font(files["MintSans/otf/MintSans-BoldItalic.otf"])
        top = otf["CFF "].cff.topDictIndex[0]
        self.assertEqual(top.ItalicAngle, fx.ITALIC_ANGLE)
        self.assertEqual(top.FamilyName, "Mint Sans")
        self.assertEqual(top.UnderlinePosition, otf["post"].underlinePosition)

    def test_style_name_on_italic(self):
        files = mint(fx.variable_ttf(italic=True),
                     Options(name="Mint Sans", axes={"wght": "375"}, style_name="Regular", formats={"ttf"}, hint=False))
        self.assertEqual(list(files), ["MintSans/ttf-unhinted/MintSans-Italic.ttf"])


class AxisOptionsTest(unittest.TestCase):
    def build(self, **kw):
        kw.setdefault("formats", {"ttf"})
        kw.setdefault("hint", False)
        kw.setdefault("name", "Mint Sans")
        return mint(fx.variable_ttf(), Options(**kw))

    def test_values_are_static_only(self):
        files = self.build(axes={"wght": "400,700", "wdth": "75,100"})
        self.assertNotIn("variable", folders(files))
        self.assertEqual(sorted(p.split("/")[-1] for p in files), [
            "MintSans-Bold.ttf", "MintSans-Condensed.ttf", "MintSans-CondensedBold.ttf", "MintSans-Regular.ttf"])

    def test_custom_weight(self):
        files = self.build(axes={"wght": "375"})
        font = fx.open_font(files["MintSans/ttf-unhinted/MintSans-W375.ttf"])
        self.assertEqual(font["OS/2"].usWeightClass, 375)

    def test_style_name(self):
        files = self.build(axes={"wght": "375"}, style_name="Regular")
        font = fx.open_font(files["MintSans/ttf-unhinted/MintSans-Regular.ttf"])
        self.assertEqual((font["name"].getDebugName(2), font["OS/2"].usWeightClass), ("Regular", 375))

    def test_style_name_needs_exactly_one_static(self):
        with self.assertRaisesRegex(FontmintError, "exactly one static font"):
            self.build(axes={"wght": "400,700"}, style_name="Regular")
        with self.assertRaisesRegex(FontmintError, "exactly one static font"):
            self.build(style_name="Regular")  # default: 4 named instances

    def test_range_trims_variable_font(self):
        files = self.build(axes={"wght": "300:700"}, formats={"ttf", "woff2"})
        self.assertEqual(sorted(files), ["MintSans/variable/MintSans-wght300-700[wght,wdth].ttf",
                                         "MintSans/variable/MintSans-wght300-700[wght,wdth].woff2"])
        axes = {a.axisTag: (a.minValue, a.maxValue) for a in fx.open_font(next(iter(files.values())))["fvar"].axes}
        self.assertEqual(axes, {"wght": (300, 700), "wdth": (75, 100)})  # unmentioned axis keeps full range

    def test_range_with_pinned_axis(self):
        files = self.build(axes={"wght": "300:700", "wdth": "75"})
        path = "MintSans/variable/MintSans-wght300-700-Condensed[wght].ttf"
        self.assertEqual(list(files), [path])
        self.assertEqual([a.axisTag for a in fx.open_font(files[path])["fvar"].axes], ["wght"])

    def test_mixed_values_and_ranges(self):
        files = self.build(axes={"wght": "400,300:700"})
        self.assertEqual(sorted(files), ["MintSans/ttf-unhinted/MintSans-Regular.ttf",
                                         "MintSans/variable/MintSans-wght300-700[wght,wdth].ttf"])

    def test_formats_subset(self):
        self.assertEqual(folders(self.build(axes={"wght": "400"}, formats={"otf"})), {"otf"})
        self.assertEqual(folders(self.build(axes={"wght": "400"}, formats={"woff2"}, hint=True)),
                         {"woff2-unhinted", "woff2-hinted"})

    def test_range_with_only_otf_is_reported(self):
        """Variable fonts are written as TTF/WOFF2 only - asking for a range in OTF
        alone would silently produce nothing."""
        with self.assertRaisesRegex(FontmintError, "variable fonts are written as ttf/woff2"):
            self.build(axes={"wght": "300:700"}, formats={"otf"})

    def test_default_with_only_otf_warns_about_variable(self):
        p = prepare(fx.variable_ttf(), Options(name="Mint Sans", formats={"otf"}))
        self.assertEqual(p.files, {})
        self.assertTrue(any("variable font is skipped" in w for w in p.warnings))

    def test_equal_range_is_a_value(self):
        files = self.build(axes={"wght": "400:400"})
        self.assertEqual(list(files), ["MintSans/ttf-unhinted/MintSans-Regular.ttf"])

    def test_tuple_is_a_range(self):
        files = self.build(axes={"wght": (300, 700)})
        self.assertEqual(list(files), ["MintSans/variable/MintSans-wght300-700[wght,wdth].ttf"])

    def test_names_are_tidied_and_checked(self):
        files = self.build(name="  Mint   Sans ", axes={"wght": "400"})
        font = fx.open_font(next(iter(files.values())))
        self.assertEqual(font["name"].getDebugName(1), "Mint Sans")
        with self.assertRaisesRegex(FontmintError, "may only use"):
            self.build(name='Foo:Bar*', axes={"wght": "400"})

    def test_original_name_warns(self):
        p = prepare(fx.variable_ttf(), Options(name="Test Sans"))
        self.assertTrue(any("original family name" in w for w in p.warnings))

    def test_features_none(self):
        self.assertTrue(self.build(features=None, axes={"wght": "400"}))

    def test_options_accept_strings_and_lists(self):
        files = mint(fx.variable_ttf(), Options(name="Mint Sans", features=["ss01"], axes={"wght": "400"},
                                                formats="ttf", hint=False))
        self.assertEqual(fx.open_font(next(iter(files.values()))).getBestCmap()[ord("0")], "zero.ss01")

    def test_unfreezable_feature_warns(self):
        p = prepare(fx.variable_ttf(), Options(name="Mint Sans", features="liga"))
        self.assertEqual(p.frozen, 0)
        self.assertTrue(any("changed nothing" in w for w in p.warnings))

    def test_variable_without_name_warns(self):
        p = prepare(fx.variable_ttf(), Options(axes={"wght": "300:700"}))
        self.assertTrue(any("no --name given" in w for w in p.warnings))

    def test_invalid_names(self):
        for bad in ("a/../../Esc", "Clär", ".."):
            with self.subTest(name=bad), self.assertRaises(FontmintError):
                self.build(name=bad, axes={"wght": "400"})

    def test_invalid_options(self):
        with self.assertRaisesRegex(FontmintError, "unknown format"):
            self.build(formats={"pdf"})
        with self.assertRaisesRegex(FontmintError, "outside"):
            self.build(axes={"wght": "1000"})
        with self.assertRaisesRegex(FontmintError, "not a readable font"):
            mint(b"definitely not a font")
        with self.assertRaisesRegex(FontmintError, r"collections \(.ttc\)"):
            mint(b"ttcf" + b"\0" * 32)


class InspectTest(unittest.TestCase):
    def test_variable(self):
        info = inspect(fx.variable_ttf())
        self.assertTrue(info.variable)
        self.assertEqual([a[0] for a in info.axes], ["wght", "wdth"])
        self.assertEqual([n for n, _ in info.instances], ["Regular", "Bold", "Condensed", "Condensed Bold"])
        self.assertEqual(info.features, ["liga", "ss01"])

    def test_static(self):
        info = inspect(fx.static_otf())
        self.assertFalse(info.variable)
        self.assertEqual((info.axes, info.instances, info.family), ([], [], "Test Sans"))


class NativeHelpersOptionalTest(unittest.TestCase):
    def test_no_native_modules_when_disabled(self):
        """With hint/remove_overlaps/subroutinize off, ttfautohint, skia-pathops and
        cffsubr are never imported - the core can run where they don't exist."""
        code = (
            "import sys\n"
            "from tests import fixtures as fx\n"
            "from fontmint import Options, mint\n"
            "options = Options(name='X', hint=False, remove_overlaps=False, subroutinize=False)\n"
            "files = mint(fx.variable_ttf(), options)\n"
            "assert any('/otf/' in p for p in files)\n"
            "print(sorted(m for m in ('ttfautohint', 'cffsubr', 'pathops') if m in sys.modules))\n"
        )
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
