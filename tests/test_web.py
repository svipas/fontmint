"""web/fontmint_web.py - the glue the browser page calls - on desktop Python."""

import io
import json
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from fontmint import FontmintError

from . import fixtures as fx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
import fontmint_web as web  # noqa: E402


def run(font: bytes, options: dict, name: str = "TestSans.ttf") -> tuple[list[str], dict, list[dict]]:
    """prepare() + build() one font: (planned paths, files, reported events)."""
    events: list[dict] = []
    paths = web.prepare(name, font, options, events.append)["paths"]
    files = web.build(name, events.append)
    return paths, files, events


def logged(events: list[dict], warning: bool = False) -> list[str]:
    return [e["text"] for e in events if e["type"] == "log" and e["warning"] == warning]


class DescribeTest(unittest.TestCase):
    def test_variable(self):
        info = web.describe("TestSans.ttf", fx.variable_ttf())
        json.dumps(info)  # plain values only: the worker hands them to JavaScript
        self.assertTrue(info["variable"])
        self.assertFalse(info["cff2"])
        self.assertEqual([a[0] for a in info["axes"]], ["wght", "wdth"])
        self.assertEqual(info["feature_names"], {"ss01": "Slashed zero"})
        self.assertEqual(info["changes"], {"ss01": [ord("0"), ord("I")]})

    def test_cff2_and_static(self):
        self.assertTrue(web.describe("TestSans.otf", fx.variable_cff2())["cff2"])
        info = web.describe("TestSans.otf", fx.static_otf())
        self.assertEqual((info["variable"], info["cff2"]), (False, False))

    def test_unreadable_font_names_the_file(self):
        with self.assertRaisesRegex(FontmintError, "^Broken.ttf: not a readable font"):
            web.describe("Broken.ttf", b"not a font")


class VariableBuildTest(unittest.TestCase):
    def test_default_build_is_unhinted_ttf_and_woff2(self):
        with (
            mock.patch("fontmint.core.autohint", side_effect=AssertionError("hinted")),
            mock.patch("fontmint.core.ttf_to_otf", side_effect=AssertionError("otf")),
        ):
            paths, files, events = run(fx.variable_ttf(), {"features": "ss01", "name": "Mint Sans"})

        self.assertEqual({p.split("/")[1] for p in files}, {"variable", "ttf-unhinted", "woff2-unhinted"})
        self.assertEqual(len(files), 2 + 4 * 2)  # variable TTF + WOFF2, 4 named instances × 2 formats
        self.assertEqual(len(paths), 2 + 4)  # files ready now + one per job
        self.assertEqual(logged(events), ["froze ss01: 2 characters remapped"])
        jobs = [e for e in events if e["type"] == "job"]
        self.assertEqual([(e["done"], e["total"]) for e in jobs], [(1, 4), (2, 4), (3, 4), (4, 4)])
        self.assertEqual(jobs[0]["style"], "MintSans-Regular")
        self.assertEqual(jobs[0]["font"], "TestSans.ttf")
        self.assertEqual(jobs[1]["location"], {"wght": 700, "wdth": 100})
        self.assertEqual(jobs[1]["where"], "wght 700, wdth 100")

    def test_jobs_say_where_on_the_axes(self):
        _, _, events = run(fx.variable_ttf(), {"name": "Mint Sans", "axes": {"wght": "375,300:700"}, "style_name": ""})
        self.assertEqual(
            [(e["style"], e["where"]) for e in events if e["type"] == "job"],
            [("MintSans-W375", "wght 375, wdth 100"), ("MintSans-wght300-700[wght,wdth]", "wght 300–700")],
        )

    def test_several_named_styles_in_one_build(self):
        styles = [{"axes": {"wght": "375"}, "style_name": "Regular"}, {"axes": {"wght": "675"}, "style_name": "Bold"}]
        paths, files, events = run(fx.variable_ttf(), {"name": "Mint Sans", "formats": ["ttf"], "styles": styles})
        self.assertEqual(
            sorted(files), ["MintSans/ttf-unhinted/MintSans-Bold.ttf", "MintSans/ttf-unhinted/MintSans-Regular.ttf"]
        )
        self.assertEqual(len(paths), 2)
        self.assertEqual(
            [(e["style"], e["where"], e["done"], e["total"]) for e in events if e["type"] == "job"],
            [("MintSans-Regular", "wght 375, wdth 100", 1, 2), ("MintSans-Bold", "wght 675, wdth 100", 2, 2)],
        )
        self.assertEqual(logged(events, warning=True), [])

    def test_two_styles_building_the_same_font(self):
        styles = [{"axes": {"wght": "375"}, "style_name": "Book"}, {"axes": {"wght": "400"}, "style_name": "Book"}]
        with self.assertRaisesRegex(FontmintError, "^TestSans.ttf: two styles would both build MintSans-Book: "):
            web.prepare("TestSans.ttf", fx.variable_ttf(), {"name": "Mint Sans", "styles": styles}, print)

    def test_prepare_counts_jobs(self):
        plan = web.prepare("TestSans.ttf", fx.variable_ttf(), {"name": "Mint Sans"}, print)
        self.assertEqual((plan["jobs"], plan["folder"]), (4, "MintSans"))

    def test_formats_and_axes(self):
        _, files, _ = run(fx.variable_ttf(), {"name": "Mint Sans", "formats": ["woff2"], "axes": {"wght": "300:700"}})
        self.assertEqual(list(files), ["MintSans/variable/MintSans-wght300-700[wght,wdth].woff2"])

    def test_static_otf_needs_the_cli(self):
        with self.assertRaisesRegex(FontmintError, "^TestSans.ttf: static OTF fonts need the fontmint command line"):
            web.prepare("TestSans.ttf", fx.variable_ttf(), {"formats": ["otf", "ttf"]}, print)

    def test_hinting_option_is_ignored(self):
        _, files, _ = run(fx.variable_ttf(hinted=True), {"name": "Mint Sans", "hint": True})
        self.assertNotIn("ttf-hinted", {p.split("/")[1] for p in files})

    def test_warnings_are_marked(self):
        _, _, events = run(fx.variable_ttf(), {})
        self.assertTrue(any("no --name given" in text for text in logged(events, warning=True)))

    def test_errors_name_the_file(self):
        with self.assertRaisesRegex(FontmintError, r"^TestSans.ttf: --line-height 9 is out of range"):
            web.prepare("TestSans.ttf", fx.variable_ttf(), {"line_height": 9}, print)

    def test_failed_job_names_the_file_and_style(self):
        web.prepare("TestSans.ttf", fx.variable_ttf(), {"name": "Mint Sans"}, print)
        with (
            mock.patch("fontmint_web.build_job", side_effect=ValueError("broken outline")),
            self.assertRaisesRegex(FontmintError, "^TestSans.ttf: MintSans-Regular: broken outline"),
        ):
            web.build("TestSans.ttf", print)


class Cff2BuildTest(unittest.TestCase):
    def test_variable_font_stays_otf(self):
        _, files, events = run(fx.variable_cff2(), {"name": "Mint Sans", "formats": ["otf", "woff2"]})
        self.assertEqual(
            sorted(files), ["MintSans/variable/MintSans[wght].otf", "MintSans/variable/MintSans[wght].woff2"]
        )
        self.assertTrue(any("only the variable font is built" in text for text in logged(events, warning=True)))


class StaticInputTest(unittest.TestCase):
    def test_keeps_its_format_without_warnings(self):
        # The page sends its usual options; static input ignores the output ones quietly.
        _, files, events = run(
            fx.static_otf(),
            {"features": "ss01", "name": "Mint Sans", "formats": ["ttf", "woff2"], "static": True},
            name="TestSans-Regular.otf",
        )
        self.assertEqual(list(files), ["MintSans/MintSans-Regular.otf"])
        self.assertEqual(logged(events, warning=True), [])
        self.assertEqual([e for e in events if e["type"] == "job"], [])


class ClashAndZipTest(unittest.TestCase):
    def test_one_worker_several_fonts(self):
        events: list[dict] = []
        web.prepare("Upright.ttf", fx.variable_ttf(), {"name": "Mint Sans", "static": False}, events.append)
        web.prepare("Italic.ttf", fx.variable_ttf(italic=True), {"name": "Mint Sans", "static": False}, events.append)
        self.assertEqual(
            list(web.build("Italic.ttf", print)),
            ["MintSans/variable/MintSans-Italic[wght,wdth].ttf", "MintSans/variable/MintSans-Italic[wght,wdth].woff2"],
        )
        self.assertEqual(len(web.build("Upright.ttf", print)), 2)

    def test_two_inputs_writing_the_same_file(self):
        paths = web.prepare("TestSans.ttf", fx.variable_ttf(), {"name": "Mint Sans"}, print)["paths"]
        with self.assertRaisesRegex(FontmintError, "two inputs would both write"):
            web.check_clashes([paths, paths])

    def test_zip_has_the_cli_layout(self):
        files = {"MintSans/woff2-unhinted/MintSans-Bold.woff2": b"b", "MintSans/variable/MintSans[wght].ttf": b"v"}
        events: list[dict] = []
        archive = zipfile.ZipFile(io.BytesIO(web.zip_files(files, events.append)))
        self.assertEqual(archive.namelist(), sorted(files))
        self.assertEqual(archive.read("MintSans/variable/MintSans[wght].ttf"), b"v")
        self.assertEqual([e["path"] for e in events], sorted(files))


class NativeHelpersTest(unittest.TestCase):
    def test_never_imported(self):
        """In a fresh process, as in the browser: ttfautohint, skia-pathops and cffsubr
        are never imported."""
        code = (
            "import sys\n"
            "sys.path.insert(0, 'web')\n"
            "import fontmint_web as web\n"
            "from tests import fixtures as fx\n"
            "for font in (fx.variable_ttf(), fx.variable_cff2(), fx.static_otf()):\n"
            "    web.prepare('font', font, {'name': 'X'}, print)\n"
            "    web.build('font', print)\n"
            "print(sorted(m for m in ('ttfautohint', 'cffsubr', 'pathops') if m in sys.modules))\n"
        )
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip().splitlines()[-1], "[]")


if __name__ == "__main__":
    unittest.main()
