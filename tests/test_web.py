"""web/fontmint_web.py - the glue the browser page calls - on desktop Python."""

import io
import json
import subprocess
import sys
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from fontmint import FontmintError, Options, mint

from . import fixtures as fx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
import fontmint_web as web  # noqa: E402


def run(font: bytes, options: dict, name: str = "TestSans.ttf") -> tuple[list[str], dict, list[dict]]:
    """prepare() + build() one font: (planned paths, files, reported events)."""
    events: list[dict] = []
    plan = web.prepare(name, font, options, events.append)
    return plan["paths"], build(plan, name, events.append), events


def build(plan: dict, name: str = "TestSans.ttf", report=lambda event: None) -> dict[str, bytes]:
    """Every file of a plan, as the page's workers build it: job by job."""
    files = dict(plan["files"])
    for job in plan["jobs"]:
        files |= web.run_job(name, job["job"], plan["sources"][job["source"]], report)
    return files


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

    def test_damage_is_found_even_in_tables_the_page_does_not_show(self):
        font = fx.open_font(fx.variable_ttf())
        damaged = {}
        for tag in ("gvar", "GSUB"):
            entry = font.reader.tables[tag]
            data = bytearray(fx.variable_ttf())
            data[entry.offset : entry.offset + entry.length] = b"\xff" * entry.length
            damaged[tag] = bytes(data)

        self.assertEqual(web.describe("TestSans.ttf", damaged["gvar"])["family"], "Test Sans")
        with self.assertRaisesRegex(FontmintError, "^TestSans.ttf: not a readable font"):
            web.check("TestSans.ttf", damaged["gvar"])
        with self.assertRaisesRegex(FontmintError, "^TestSans.ttf: not a readable font"):
            web.describe("TestSans.ttf", damaged["GSUB"])
        web.check("TestSans.ttf", fx.variable_ttf())


class VariableBuildTest(unittest.TestCase):
    def test_default_build_is_unhinted_ttf_and_woff2(self):
        with (
            mock.patch("fontmint.core.autohint", side_effect=AssertionError("hinted")),
            mock.patch("fontmint.core.ttf_to_otf", side_effect=AssertionError("otf")),
        ):
            paths, files, events = run(fx.variable_ttf(), {"features": "ss01", "name": "Mint Sans"})

        self.assertEqual({p.split("/")[1] for p in files}, {"variable", "ttf-unhinted", "woff2-unhinted"})
        self.assertEqual(len(files), 2 + 4 * 2)  # variable TTF + WOFF2, 4 named instances × 2 formats
        self.assertEqual(len(paths), 1 + 5)  # the variable TTF, ready now + one per job
        self.assertEqual(logged(events), ["froze ss01: 2 characters remapped"])
        jobs = [e for e in events if e["type"] == "job"]
        # The variable font's WOFF2 first: it can take the longest.
        self.assertEqual([e["style"] for e in jobs[:2]], ["MintSans[wght,wdth]", "MintSans-Regular"])
        self.assertEqual(len(jobs), 5)
        self.assertEqual(jobs[0]["font"], "TestSans.ttf")
        self.assertNotIn("location", jobs[0])
        self.assertEqual(jobs[2]["location"], {"wght": 700, "wdth": 100})
        self.assertEqual(jobs[2]["where"], "wght 700, wdth 100")

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
            [(e["style"], e["where"]) for e in events if e["type"] == "job"],
            [("MintSans-Regular", "wght 375, wdth 100"), ("MintSans-Bold", "wght 675, wdth 100")],
        )
        self.assertEqual(logged(events, warning=True), [])

    def test_two_styles_building_the_same_font(self):
        styles = [{"axes": {"wght": "375"}, "style_name": "Book"}, {"axes": {"wght": "400"}, "style_name": "Book"}]
        with self.assertRaisesRegex(FontmintError, "^TestSans.ttf: two styles would both build MintSans-Book: "):
            web.prepare("TestSans.ttf", fx.variable_ttf(), {"name": "Mint Sans", "styles": styles}, print)

    def test_jobs_share_their_source(self):
        styles = [{"axes": {"wght": "375"}, "style_name": "Regular"}, {"axes": {"wght": "675"}, "style_name": "Bold"}]
        plan = web.prepare("TestSans.ttf", fx.variable_ttf(), {"name": "Mint Sans", "styles": styles}, print)
        self.assertEqual([len(plan["jobs"]), len(plan["sources"])], [2, 1])
        # The whole variable font has the letter spacing already; the jobs add it themselves.
        options = {"name": "Mint Sans", "letter_spacing": 0.1}
        plan = web.prepare("TestSans.ttf", fx.variable_ttf(), options, lambda event: None)
        self.assertEqual([job["source"] for job in plan["jobs"]], [0, 1, 1, 1, 1])

    def test_the_font_is_not_checked_again(self):
        with mock.patch("fontTools.ttLib.TTFont.ensureDecompiled", side_effect=AssertionError("checked")):
            web.prepare("TestSans.ttf", fx.variable_ttf(), {"name": "Mint Sans"}, print)

    def test_builds_what_the_library_builds(self):
        options: dict = {"features": "ss01", "name": "Mint Sans", "letter_spacing": 0.1, "formats": ["ttf", "woff2"]}
        with mock.patch.dict("os.environ", SOURCE_DATE_EPOCH="0"):
            _, files, _ = run(fx.variable_ttf(hinted=True), options)
            expected = mint(fx.variable_ttf(hinted=True), Options(**options, hint=False))
        self.assertEqual(files, expected)

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
        plan = web.prepare("TestSans.ttf", fx.variable_ttf(), {"name": "Mint Sans", "formats": ["ttf"]}, print)
        with (
            mock.patch("fontmint_web.build_job", side_effect=ValueError("broken outline")),
            self.assertRaisesRegex(FontmintError, "^TestSans.ttf: MintSans-Regular: broken outline"),
        ):
            build(plan)

    def test_running_out_of_memory_says_what_to_do(self):
        plan = web.prepare("TestSans.ttf", fx.variable_ttf(), {"name": "Mint Sans", "formats": ["ttf"]}, print)
        with (
            mock.patch("fontmint_web.build_job", side_effect=MemoryError),
            self.assertRaisesRegex(FontmintError, "MintSans-Regular: out of memory; build with fewer workers"),
        ):
            build(plan)


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
    def test_two_inputs_writing_the_same_file(self):
        paths = web.prepare("TestSans.ttf", fx.variable_ttf(), {"name": "Mint Sans"}, print)["paths"]
        with self.assertRaisesRegex(FontmintError, "two inputs would both write"):
            web.check_clashes([paths, paths])

    def test_zip_has_the_cli_layout(self):
        files = {"MintSans/woff2-unhinted/MintSans-Bold.woff2": b"b", "MintSans/variable/MintSans[wght].ttf": b"v"}
        events: list[dict] = []
        archive = zipfile.ZipFile(io.BytesIO(web.zip_files(files, [], "1.2.3", events.append)))
        self.assertEqual(archive.namelist(), sorted(files))
        self.assertEqual(archive.read("MintSans/variable/MintSans[wght].ttf"), b"v")
        self.assertEqual([e["path"] for e in events], sorted(files))

    def test_zip_has_a_report(self):
        styles = [{"axes": {"wght": "375"}, "style_name": "Regular"}, {"axes": {"wght": "675"}, "style_name": "Bold"}]
        options = {"name": "Mint Sans", "formats": ["ttf", "woff2"], "styles": styles}
        plan = web.prepare("TestSans.ttf", fx.variable_ttf(), options, lambda event: None)
        entry = json.loads(json.dumps(plan["entry"]))  # plain values only: it goes through JavaScript
        files = build(plan)
        archive = zipfile.ZipFile(io.BytesIO(web.zip_files(files, [entry], "1.2.3", lambda event: None)))
        self.assertEqual(archive.namelist(), sorted([*files, "MintSans/fontmint.txt"]))
        report = archive.read("MintSans/fontmint.txt").decode()
        self.assertIn("Made with       the fontmint website 1.2.3 (https://svipas.github.io/fontmint)\n", report)
        self.assertIn('    Styles          weight 375 as "Regular"\n                    weight 675 as "Bold"\n', report)
        self.assertIn("--weight 375 --style-name Regular --formats ttf,woff2 --no-hint\n", report)
        self.assertIn("\n  ttf-unhinted/MintSans-Bold.ttf\n", report)


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
            "    plan = web.prepare('font', font, {'name': 'X'}, print)\n"
            "    for job in plan['jobs']:\n"
            "        web.run_job('font', job['job'], plan['sources'][job['source']], print)\n"
            "print(sorted(m for m in ('ttfautohint', 'cffsubr', 'pathops') if m in sys.modules))\n"
        )
        out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertEqual(out.stdout.strip().splitlines()[-1], "[]")


if __name__ == "__main__":
    unittest.main()
