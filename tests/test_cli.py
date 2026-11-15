import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fontmint.cli import main

from . import fixtures as fx


class CliTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.out = self.tmp / "dist"
        (self.tmp / "TestSans[wght,wdth].ttf").write_bytes(fx.variable_ttf())
        (self.tmp / "TestSans-Regular.otf").write_bytes(fx.static_otf())

    def tearDown(self):
        self._tmp.cleanup()

    def run_cli(self, *args) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        code = 0
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                main([*map(str, args)])
            except SystemExit as e:
                code = e.code or 0
        return code, stdout.getvalue(), stderr.getvalue()

    def written(self) -> list[str]:
        return sorted(str(p.relative_to(self.out)) for p in self.out.rglob("*") if p.is_file())

    def test_variable_with_axis_values(self):
        code, _, err = self.run_cli(self.tmp / "TestSans[wght,wdth].ttf", "--features", "ss01", "--name", "Mint Sans",
                                    "--weight", "400,700", "--formats", "ttf", "--output", self.out, "--jobs", "2")
        self.assertEqual(code, 0, err)
        self.assertIn("froze ss01: 2 characters remapped", err)
        self.assertEqual(self.written(), [
            "MintSans/ttf-hinted/MintSans-Bold.ttf", "MintSans/ttf-hinted/MintSans-Regular.ttf",
            "MintSans/ttf-unhinted/MintSans-Bold.ttf", "MintSans/ttf-unhinted/MintSans-Regular.ttf"])

    def test_static_passthrough(self):
        code, _, err = self.run_cli(self.tmp / "TestSans-Regular.otf", "--features", "ss01", "--name", "Mint Sans",
                                    "--output", self.out)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written(), ["MintSans/MintSans-Regular.otf"])

    def test_custom_axis_flag(self):
        code, _, err = self.run_cli(self.tmp / "TestSans[wght,wdth].ttf", "--name", "Mint Sans", "--axis", "wdth=75",
                                    "--formats", "otf", "--output", self.out)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written(), ["MintSans/otf/MintSans-Condensed.otf"])

    def test_bad_second_font_writes_nothing(self):
        """All inputs are checked before anything is written."""
        (self.tmp / "broken.ttf").write_bytes(b"not a font")
        code, _, err = self.run_cli(self.tmp / "TestSans[wght,wdth].ttf", self.tmp / "broken.ttf",
                                    "--name", "Mint Sans", "--formats", "ttf", "--output", self.out)
        self.assertEqual(code, 1)
        self.assertIn("broken.ttf: not a readable font", err)
        self.assertFalse(self.out.exists(), self.written() if self.out.exists() else "")

    def test_unhintable_font_needs_no_hint(self):
        (self.tmp / "Arrows.ttf").write_bytes(fx.symbol_variable_ttf())
        args = (self.tmp / "Arrows.ttf", "--name", "Arrows X", "--weight", "400", "--formats", "ttf",
                "--output", self.out)
        code, _, err = self.run_cli(*args)
        self.assertEqual(code, 1)
        self.assertIn("ttfautohint can't hint this font", err)
        self.assertNotIn("Traceback", err)
        self.assertFalse(self.out.exists(), "a failed build job must not leave files behind")
        code, _, err = self.run_cli(*args, "--no-hint")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written(), ["ArrowsX/ttf-unhinted/ArrowsX-Regular.ttf"])

    def test_inputs_writing_the_same_files(self):
        code, _, err = self.run_cli(self.tmp / "TestSans[wght,wdth].ttf", self.tmp / "TestSans[wght,wdth].ttf",
                                    "--name", "Mint Sans", "--weight", "400", "--output", self.out)
        self.assertEqual(code, 1)
        self.assertIn("two inputs would both write MintSans-Regular into MintSans/", err)
        self.assertFalse(self.out.exists())

    def test_output_is_a_file(self):
        blocker = self.tmp / "not-a-dir"
        blocker.write_text("x")
        code, _, err = self.run_cli(self.tmp / "TestSans-Regular.otf", "--name", "Mint Sans", "--output", blocker)
        self.assertEqual(code, 1)
        self.assertIn("can't write", err)
        self.assertNotIn("Traceback", err)

    def test_unwritable_output_fails_before_building(self):
        locked = self.tmp / "locked"
        locked.mkdir()
        locked.chmod(0o555)
        code, _, err = self.run_cli(self.tmp / "TestSans[wght,wdth].ttf", "--name", "Mint Sans",
                                    "--output", locked / "dist")
        self.assertEqual(code, 1)
        self.assertIn("no write permission", err)
        self.assertNotIn("building", err)

    def test_existing_output_folder_warns(self):
        args = (self.tmp / "TestSans-Regular.otf", "--name", "Mint Sans", "--output", self.out)
        self.assertEqual(self.run_cli(*args)[0], 0)
        code, _, err = self.run_cli(*args)
        self.assertEqual(code, 0)
        self.assertIn("already exists; files from earlier runs are kept", err)

    def test_version(self):
        code, out, _ = self.run_cli("--version")
        self.assertEqual(code, 0)
        self.assertRegex(out, r"^fontmint \d+\.\d+\.\d+")

    def test_help_works_without_docstrings(self):
        """python -OO strips docstrings; --help must still work."""
        result = subprocess.run([sys.executable, "-OO", "-m", "fontmint", "--help"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--weight VALUES", result.stdout)

    def test_list_features(self):
        code, out, _ = self.run_cli(self.tmp / "TestSans[wght,wdth].ttf", self.tmp / "TestSans-Regular.otf",
                                    "--list-features")
        self.assertEqual(code, 0)
        self.assertIn("instances: Regular, Bold, Condensed, Condensed Bold", out)
        self.assertIn("static font", out)
        self.assertIn("features:  liga ss01", out)

    def test_errors(self):
        cases = [
            (("--weight", "400"), 1, "only apply to variable fonts", "TestSans-Regular.otf"),
            (("--weight", "950"), 1, "outside the axis range", "TestSans[wght,wdth].ttf"),
            (("--weight", "bold"), 1, "invalid axis value", "TestSans[wght,wdth].ttf"),
            (("--weight", "400", "--axis", "wght=700"), 1, "given twice", "TestSans[wght,wdth].ttf"),
            (("--axis", "wdth"), 1, "TAG=VALUES", "TestSans[wght,wdth].ttf"),
            (("--formats", "pdf"), 1, "unknown format", "TestSans[wght,wdth].ttf"),
            (("--static", "400"), 2, "unrecognized arguments", "TestSans[wght,wdth].ttf"),
            (("-n", "X"), 2, "unrecognized arguments", "TestSans[wght,wdth].ttf"),
            (("--nam", "X"), 2, "unrecognized arguments", "TestSans[wght,wdth].ttf"),
            ((), 1, "missing.ttf: No such file or directory", "missing.ttf"),
            (("--jobs", "0"), 2, "at least 1", "TestSans[wght,wdth].ttf"),
            (("--axis", "XXXX=1", "--axis", "XXXX=2"), 1, "axis 'XXXX' given twice\n", "TestSans[wght,wdth].ttf"),
            (("--width", "75", "--axis", "wdth=100"), 1, "use either --width or --axis wdth=", "TestSans[wght,wdth].ttf"),
            (("--list-features",), 1, "No such file or directory", "missing.ttf"),
            (("--name", "a/../../Esc"), 1, "--name may only use", "TestSans-Regular.otf"),
        ]
        for args, expected_code, message, font in cases:
            with self.subTest(args=args):
                code, _, err = self.run_cli(self.tmp / font, *args, "--output", self.out)
                self.assertEqual(code, expected_code, err)
                self.assertIn(message, err)
        self.assertFalse(self.out.exists(), "failed runs must not write files")


if __name__ == "__main__":
    unittest.main()
