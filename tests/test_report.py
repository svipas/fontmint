import shlex
import unittest

from fontTools.ttLib import TTFont

from fontmint import Options, prepare
from fontmint.cli import _join_negative_axis_values, build_parser
from fontmint.common import to_bytes
from fontmint.report import Entry, log_lines, make_entry, render

from . import fixtures as fx


def entry(font: bytes, *options: Options, name: str = "TestSans.ttf") -> Entry:
    return make_entry(name, font, options, prepare(font, options[0]))


def text(entries: list[Entry], paths: list[str] | None = None) -> str:
    (data,) = render(entries, paths or [], "fontmint 1.2.3").values()
    return data.decode()


def named(font: bytes, name_id: int, value: str) -> bytes:
    opened: TTFont = fx.open_font(font)
    opened["name"].setName(value, name_id, 3, 1, 0x409)
    return to_bytes(opened)


class ChangesTest(unittest.TestCase):
    def test_lists_every_change(self):
        options = Options(
            features="ss01",
            disable="liga",
            line_height=1.4,
            letter_spacing=0.02,
            subset="latin,U+2190",
            name="Mint Sans",
            axes={"wght": "375,500:700", "wdth": "75"},
            formats="woff2,ttf",
            hint=False,
        )
        result = entry(fx.variable_ttf(), options)
        self.assertEqual(
            result.changes,
            [
                "Family name     Mint Sans (was Test Sans)",
                "Made default    ss01  Slashed zero",
                "Turned off      liga",
                "Line height     1.4 (was 1.00)",
                "Letter spacing  +0.02 em",
                "Characters      latin, U+2190",
                "Styles          weight 375, 500–700, width 75",
                "Formats         ttf, woff2",
                "Hinting         no hinted static fonts",
            ],
        )
        self.assertEqual(result.note, "(kept 8 of 8 characters)")

    def test_alternates_and_languages(self):
        options = Options(features="ss01=2,liga", language="rom")
        prepared = prepare(fx.static_otf(), Options())
        self.assertEqual(
            make_entry("f.otf", fx.static_otf(), [options], prepared).changes,
            ["Made default    ss01=2  Slashed zero", "                liga", "Language        ROM"],
        )

    def test_features_turned_off_have_their_names(self):
        self.assertEqual(
            entry(fx.static_otf(), Options(disable="ss01,liga")).changes,
            ["Turned off      ss01  Slashed zero", "                liga"],
        )

    def test_output_options_are_no_changes_to_static_input(self):
        options = Options(formats="ttf", static=False, hint=False)
        self.assertEqual(entry(fx.static_otf(), options).changes, [])

    def test_style_name_alone(self):
        options = Options(style_name="Book")
        prepared = prepare(fx.variable_ttf(), Options())
        self.assertEqual(
            make_entry("f.ttf", fx.variable_ttf(), [options], prepared).changes, ['Styles          as "Book"']
        )

    def test_large_numbers_are_readable(self):
        prepared = prepare(fx.static_otf(), Options())
        prepared.subset = (1000, 23456)
        options = Options(subset="latin")
        self.assertEqual(
            make_entry("f.otf", fx.static_otf(), [options], prepared).note, "(kept 1,000 of 23,456 characters)"
        )

    def test_name_that_stays_is_no_change(self):
        self.assertEqual(entry(fx.static_otf(), Options(name="Test Sans")).changes, [])

    def test_hinting_is_only_mentioned_for_static_fonts(self):
        for options in (Options(hint=False, axes={"wght": "300:700"}), Options(hint=False, static=False)):
            self.assertNotIn("Hinting", "".join(entry(fx.variable_ttf(), options).changes))
        self.assertEqual(entry(fx.variable_cff2(), Options(hint=False)).changes, [])

    def test_only_what_was_asked_for(self):
        for font in (fx.static_otf(), fx.variable_ttf()):
            result = entry(font, Options())
            self.assertEqual(result.changes, [])
            self.assertIn("    No changes\n", text([result]))

    def test_several_values_continue_below_the_label(self):
        styles = [
            Options(name="Mint Sans", axes={"wght": "375"}, style_name="Regular"),
            Options(name="Mint Sans", axes={"wght": "675"}, style_name="Bold"),
        ]
        result = entry(fx.variable_ttf(), *styles)
        self.assertEqual(
            result.changes[1:], ['Styles          weight 375 as "Regular"', '                weight 675 as "Bold"']
        )
        self.assertEqual(
            result.commands,
            [
                '--name "Mint Sans" --weight 375 --style-name Regular',
                '--name "Mint Sans" --weight 675 --style-name Bold',
            ],
        )

    def test_source_has_the_version(self):
        for version, source in [
            ("Version 4.001;git-66647c0bb", "Test Sans 4.001"),
            ("Version 3.5; ttfautohint (v1.8)", "Test Sans 3.5"),
            ("1.005;PS 001.005", "Test Sans 1.005"),
            ("Build 2024-03-01; Version 1.2", "Test Sans 1.2"),
            ("Acme 3D Sans", "Test Sans"),
        ]:
            with self.subTest(version=version):
                self.assertEqual(entry(named(fx.static_otf(), 5, version), Options()).source, source)


class CommandTest(unittest.TestCase):
    def parsed(self, arguments: str):
        return build_parser().parse_args(_join_negative_axis_values([*shlex.split(arguments), "--", "Font.ttf"]))

    def test_the_command_line_reads_the_same_options(self):
        options = Options(
            features={"ss01": 2, "zero": 1},
            language="rom",
            disable=["liga"],
            line_height=1.25,
            letter_spacing=-0.12345678,
            subset=["latin", "U+20AC"],
            name="It's Mint",
            axes={"wght": [400, (300, 700), "all"], "slnt": "-10,0", "MONO": 0.5},
            style_name="-Book",
            formats="otf",
        )
        (arguments,) = make_entry("f.ttf", fx.variable_ttf(), [options], prepare(fx.variable_ttf(), Options())).commands
        args = self.parsed(arguments)
        self.assertEqual(
            (args.features, args.language, args.disable, args.line_height, args.letter_spacing, args.subset),
            ("ss01=2,zero=1", "ROM", "liga", 1.25, -0.12345678, "latin,U+20AC"),
        )
        self.assertEqual((args.name, args.style_name, args.formats), ("It's Mint", "-Book", "otf"))
        self.assertEqual((args.weight, args.slant, args.axis), (["400,300:700,all"], ["-10,0"], ["MONO=0.5"]))
        self.assertEqual((args.no_static, args.no_hint), (False, False))

    def test_values_that_start_with_an_equals_sign(self):
        (arguments,) = entry(fx.static_otf(), Options(name="=Foo")).commands
        self.assertEqual(arguments, "--name==Foo")
        self.assertEqual(self.parsed(arguments).name, "=Foo")

    def test_small_negative_values_are_not_taken_for_options(self):
        (arguments,) = entry(fx.static_otf(), Options(letter_spacing=-0.00001)).commands
        self.assertEqual(self.parsed(arguments).letter_spacing, -0.00001)

    def test_output_options(self):
        for options, arguments in [
            (Options(formats="woff2,ttf", hint=False), "--formats ttf,woff2 --no-hint"),
            (Options(static=False, hint=False), "--no-static"),
            (Options(formats="ttf,otf,woff2"), ""),
        ]:
            self.assertEqual(entry(fx.variable_ttf(), options).commands, [arguments])

    def test_one_command_for_variable_and_static_input(self):
        options = Options(name="Mint Sans", formats="ttf", hint=False)
        report = text([entry(fx.variable_ttf(), options, name="V.ttf"), entry(fx.static_otf(), options, name="S.otf")])
        self.assertIn('\n  fontmint V.ttf S.otf --name "Mint Sans" --formats ttf --no-hint\n\n', report)

    def test_file_names_the_shell_would_misread(self):
        for name, quoted in [
            ("-V.ttf", "./-V.ttf"),
            ("=V.ttf", "./=V.ttf"),
            ("V[wght].ttf", '"V[wght].ttf"'),
            ("a\u00a0b.ttf", '"a\u00a0b.ttf"'),
            ("it's.ttf", '"it\'s.ttf"'),
            *((f"a {c}.ttf", f"'a {c}.ttf'") for c in '"$`\\!'),
        ]:
            with self.subTest(name=name):
                report = text([entry(fx.static_otf(), Options(), name=name)])
                self.assertIn(f"\n  fontmint {quoted}\n", report)


class LogLinesTest(unittest.TestCase):
    def test_every_change(self):
        options = Options(
            features="ss01", language="rom", disable="liga", line_height=1.4, letter_spacing=0.02, subset="latin"
        )
        prepared = prepare(fx.static_otf(), Options(features="ss01", subset="latin"))
        self.assertEqual(
            log_lines(options, prepared),
            [
                "froze ss01 (ROM): 2 characters remapped",
                "disabled liga",
                "line height 1.4",
                "letter spacing +0.02 em",
                "subset latin: kept 8 of 8 characters",
            ],
        )
        self.assertEqual(log_lines(Options(), prepare(fx.static_otf(), Options())), [])


class RenderTest(unittest.TestCase):
    def test_whole_report(self):
        options = Options(features="ss01", name="Mint Sans", static=False, formats="ttf")
        entries = [
            entry(fx.variable_ttf(), options, name="Test Sans.ttf"),
            entry(fx.variable_ttf(italic=True), options, name="TestSans-Italic.ttf"),
        ]
        for e in entries:
            e.warnings = ["shared"]
        entries[1].warnings = ["shared", "italic only"]
        entries[1].note = "(kept 1 of 2 characters)"
        source = entries[0].source
        self.assertEqual(
            text(entries, ["MintSans/variable/b.ttf", "MintSans/variable/a.ttf"]),
            f"""Mint Sans

Made from       {source}
Made with       fontmint 1.2.3

This is a custom build, not the original font.


Changes

  Test Sans.ttf
  TestSans-Italic.ttf (kept 1 of 2 characters)
    Family name     Mint Sans (was Test Sans)
    Made default    ss01  Slashed zero
    Formats         ttf
    Static fonts    none


The same build on the command line

  fontmint "Test Sans.ttf" TestSans-Italic.ttf --features ss01 --name "Mint Sans" --formats ttf --no-static


Warnings

  - shared
  - TestSans-Italic.ttf: italic only


Files

  variable/a.ttf
  variable/b.ttf
""",
        )

    def test_fonts_with_different_changes_get_their_own_section_and_command(self):
        report = text(
            [
                entry(fx.variable_ttf(), Options(name="Mint Sans", features="ss01"), name="A.ttf"),
                entry(fx.variable_ttf(italic=True), Options(name="Mint Sans"), name="B.ttf"),
            ]
        )
        self.assertIn("  A.ttf\n    Family name     Mint Sans (was Test Sans)\n    Made default    ss01", report)
        self.assertIn("\n\n  B.ttf\n    Family name     Mint Sans (was Test Sans)\n\n", report)
        self.assertIn(
            '  fontmint A.ttf --features ss01 --name "Mint Sans"\n  fontmint B.ttf --name "Mint Sans"\n', report
        )

    def test_warnings_say_which_fonts_they_are_about(self):
        entries = [entry(fx.static_otf(), Options(name="Mint Sans"), name=name) for name in ("A.otf", "B.otf", "C.otf")]
        for e, warnings in zip(entries, (["all", "two"], ["all", "two"], ["all", "one"]), strict=True):
            e.warnings = warnings
        self.assertIn("\n  - all\n  - A.otf, B.otf: two\n  - C.otf: one\n", text(entries))

    def test_one_report_per_folder(self):
        entries = [entry(fx.static_otf(), Options(name=name)) for name in ("Mint", "Mint Sans")]
        reports = render(entries, ["Mint/a.otf", "MintSans/b.otf"], "fontmint")
        self.assertEqual(list(reports), ["Mint/fontmint.txt", "MintSans/fontmint.txt"])
        self.assertTrue(reports["Mint/fontmint.txt"].endswith(b"Files\n\n  a.otf\n"))
        self.assertTrue(reports["MintSans/fontmint.txt"].endswith(b"Files\n\n  b.otf\n"))

    def test_names_cant_add_lines(self):
        font = named(fx.static_otf(), 1, "Test\nSans\x1b[31m")
        report = text([entry(font, Options(), name="a\n\udc80b.otf")])
        self.assertIn("Made from       TestSans[31m", report)
        self.assertIn("\n  ab.otf\n", report)


if __name__ == "__main__":
    unittest.main()
