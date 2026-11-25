import contextlib
import io
import os
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
                code = int(e.code or 0)
        return code, stdout.getvalue(), stderr.getvalue()

    def written(self) -> list[str]:
        """The fonts written, next to exactly one report."""
        files = sorted(str(p.relative_to(self.out)) for p in self.out.rglob("*") if p.is_file())
        fonts = [f for f in files if not f.endswith("/fontmint.txt")]
        self.assertEqual(len(files) - len(fonts), 1)
        return fonts

    def test_variable_with_axis_values(self):
        code, _, err = self.run_cli(
            self.tmp / "TestSans[wght,wdth].ttf",
            "--features",
            "ss01",
            "--name",
            "Mint Sans",
            "--weight",
            "400,700",
            "--formats",
            "ttf",
            "--output",
            self.out,
            "--jobs",
            "2",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("froze ss01: 2 characters remapped", err)
        self.assertEqual(
            self.written(),
            [
                "MintSans/ttf-hinted/MintSans-Bold.ttf",
                "MintSans/ttf-hinted/MintSans-Regular.ttf",
                "MintSans/ttf-unhinted/MintSans-Bold.ttf",
                "MintSans/ttf-unhinted/MintSans-Regular.ttf",
            ],
        )

    def test_static_passthrough(self):
        code, _, err = self.run_cli(
            self.tmp / "TestSans-Regular.otf", "--features", "ss01", "--name", "Mint Sans", "--output", self.out
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written(), ["MintSans/MintSans-Regular.otf"])

    def test_files_that_are_not_fonts_are_skipped(self):
        (self.tmp / "OFL.txt").write_text("license")
        (self.tmp / "empty").touch()
        (self.tmp / "static").mkdir()
        (self.tmp / "no extension").write_bytes(fx.static_otf())
        (self.tmp / "TestSans-Regular.otf").unlink()
        (self.tmp / "TestSans[wght,wdth].ttf").rename(self.tmp / "TestSans.TTF")
        args = (*sorted(self.tmp.iterdir()), "--name", "Mint Sans", "--no-static")
        code, _, err = self.run_cli(*args, "--formats", "ttf", "--output", self.out)
        self.assertEqual(code, 0, err)
        for name, what in [("OFL.txt", "not a font"), ("empty", "not a font"), ("static", "a folder")]:
            self.assertIn(f"skipped {name}: {what}\n", err)
        self.assertEqual(self.written(), ["MintSans/MintSans-Regular.otf", "MintSans/variable/MintSans[wght,wdth].ttf"])
        self.assertNotIn("OFL", (self.out / "MintSans/fontmint.txt").read_text(encoding="utf-8"))

        code, out, _ = self.run_cli(*sorted(self.tmp.glob("*s*")), "--info")
        self.assertEqual((code, out.count("family:")), (0, 2))

    def test_no_fonts_at_all(self):
        (self.tmp / "OFL.txt").write_text("license")
        for paths in ([self.tmp / "OFL.txt"], [self.tmp], [self.tmp / "OFL.txt", "--info"]):
            with self.subTest(paths=paths):
                code, _, err = self.run_cli(*paths, "--output", self.out)
                self.assertEqual(code, 1)
                self.assertIn("no fonts to read", err)
        self.assertFalse(self.out.exists())

    def test_damaged_fonts_are_never_skipped(self):
        damaged = [f"Damaged{suffix}" for suffix in (".TTF", ".otf", ".woff", ".woff2", ".ttc", ".otc")]
        signed = [b"\0\1\0\0", b"OTTO", b"true", b"wOFF", b"wOF2", b"ttcf"]
        for name, data in [*((n, b"text") for n in damaged), *(("no extension", s + b"text") for s in signed)]:
            with self.subTest(name=name, data=data):
                (self.tmp / name).write_bytes(data)
                code, _, err = self.run_cli(
                    self.tmp / "TestSans-Regular.otf", self.tmp / name, "--name", "Mint Sans", "--output", self.out
                )
                self.assertEqual(code, 1)
                self.assertIn(f"error: {name}: ", err)
        self.assertFalse(self.out.exists())

    def test_unreadable_file(self):
        locked = self.tmp / "locked"
        locked.mkdir()
        (locked / "font.otf").write_bytes(fx.static_otf())
        locked.chmod(0)
        try:
            for name in ("font.otf", "no extension", "x" * 300):
                code, _, err = self.run_cli(locked / name, "--output", self.out)
                self.assertEqual(code, 1)
                self.assertIn(f"error: {name}: ", err)
        finally:
            locked.chmod(0o700)

    @unittest.skipUnless(os.path.exists("/dev/stdin"), "no /dev/stdin")
    def test_each_input_is_read_once(self):
        """A pipe can't be read twice, and on macOS neither can a redirected file."""
        font = self.tmp / "TestSans-Regular.otf"
        command = [sys.executable, "-m", "fontmint", "/dev/stdin", "--info"]
        piped = subprocess.run(command, input=font.read_bytes(), capture_output=True, timeout=60)
        self.assertEqual(piped.returncode, 0, piped.stderr)
        with font.open("rb") as file:
            redirected = subprocess.run(command, stdin=file, capture_output=True, timeout=60)
        self.assertEqual(redirected.returncode, 0, redirected.stderr)

    def test_report(self):
        args = (self.tmp / "TestSans-Regular.otf", "--name", "Mint Sans", "--output", self.out)
        code, _, err = self.run_cli(*args, "--features", "ss01")
        self.assertEqual(code, 0, err)
        self.assertTrue(err.endswith("  MintSans/fontmint.txt\ndone: 2 file(s)\n"), err)
        report = (self.out / "MintSans/fontmint.txt").read_text(encoding="utf-8")
        self.assertRegex(report, r"\nMade with       fontmint \d+\.\d+\.\d+ ")
        self.assertIn("\n    Made default    ss01  Slashed zero\n", report)
        self.assertIn('\n  fontmint TestSans-Regular.otf --features ss01 --name "Mint Sans"\n', report)
        self.assertTrue(report.endswith("\nFiles\n\n  MintSans-Regular.otf\n"), report)
        self.assertNotIn(str(self.tmp), report)  # a path can hold the user's name

        self.assertEqual(self.run_cli(*args)[0], 0)
        report = (self.out / "MintSans/fontmint.txt").read_text(encoding="utf-8")
        self.assertNotIn("ss01", report)

    def test_no_report_about_fonts_that_were_not_written(self):
        (self.out / "MintSans/variable/MintSans[wght,wdth].ttf").mkdir(parents=True)
        code, _, err = self.run_cli(
            self.tmp / "TestSans[wght,wdth].ttf", "--name", "Mint Sans", "--no-static", "--output", self.out
        )
        self.assertEqual(code, 1)
        self.assertIn("can't write", err)
        self.assertFalse((self.out / "MintSans/fontmint.txt").exists())

    def test_custom_axis_flag(self):
        code, _, err = self.run_cli(
            self.tmp / "TestSans[wght,wdth].ttf",
            "--name",
            "Mint Sans",
            "--axis",
            "wdth=75",
            "--formats",
            "otf",
            "--output",
            self.out,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written(), ["MintSans/otf/MintSans-Condensed.otf"])

    def test_no_static(self):
        code, _, err = self.run_cli(
            self.tmp / "TestSans[wght,wdth].ttf",
            "--name",
            "Mint Sans",
            "--no-static",
            "--formats",
            "woff2",
            "--output",
            self.out,
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written(), ["MintSans/variable/MintSans[wght,wdth].woff2"])

    def test_files_are_written_in_order_with_the_report_last(self):
        code, _, err = self.run_cli(
            self.tmp / "TestSans[wght,wdth].ttf", "--name", "Mint Sans", "--formats", "ttf", "--output", self.out
        )
        self.assertEqual(code, 0, err)
        written = [line.strip() for line in err.splitlines() if line.startswith("  MintSans/")]
        self.assertEqual(written, [*self.written(), "MintSans/fontmint.txt"])

    def test_bad_second_font_writes_nothing(self):
        """All inputs are checked before anything is written."""
        (self.tmp / "broken.ttf").write_bytes(b"not a font")
        code, _, err = self.run_cli(
            self.tmp / "TestSans[wght,wdth].ttf",
            self.tmp / "broken.ttf",
            "--name",
            "Mint Sans",
            "--formats",
            "ttf",
            "--output",
            self.out,
        )
        self.assertEqual(code, 1)
        self.assertIn("broken.ttf: not a readable font", err)
        self.assertFalse(self.out.exists(), self.written() if self.out.exists() else "")

    def test_unhintable_font_needs_no_hint(self):
        (self.tmp / "Arrows.ttf").write_bytes(fx.symbol_variable_ttf())
        args = (
            self.tmp / "Arrows.ttf",
            "--name",
            "Arrows X",
            "--weight",
            "400",
            "--formats",
            "ttf",
            "--output",
            self.out,
        )
        code, _, err = self.run_cli(*args)
        self.assertEqual(code, 1)
        self.assertIn("ttfautohint can't hint this font", err)
        self.assertNotIn("Traceback", err)
        self.assertFalse(self.out.exists(), "a failed build job must not leave files behind")
        code, _, err = self.run_cli(*args, "--no-hint")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.written(), ["ArrowsX/ttf-unhinted/ArrowsX-Regular.ttf"])

    def test_inputs_writing_the_same_files(self):
        code, _, err = self.run_cli(
            self.tmp / "TestSans[wght,wdth].ttf",
            self.tmp / "TestSans[wght,wdth].ttf",
            "--name",
            "Mint Sans",
            "--weight",
            "400",
            "--output",
            self.out,
        )
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
        code, _, err = self.run_cli(
            self.tmp / "TestSans[wght,wdth].ttf", "--name", "Mint Sans", "--output", locked / "dist"
        )
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

    def test_disable(self):
        code, _, err = self.run_cli(
            self.tmp / "TestSans-Regular.otf", "--disable", "liga", "--name", "Mint Sans", "--output", self.out
        )
        self.assertEqual(code, 0, err)
        self.assertIn("disabled liga", err)

    def test_info(self):
        code, out, _ = self.run_cli(self.tmp / "TestSans[wght,wdth].ttf", self.tmp / "TestSans-Regular.otf", "--info")
        self.assertEqual(code, 0)
        self.assertIn("instances:   Regular, Bold, Condensed, Condensed Bold", out)
        self.assertIn("static font", out)
        self.assertIn("features:    liga ss01\n  named:       ss01  Slashed zero\n", out)
        self.assertIn("line height: 1.00", out)
        self.assertNotIn("positioning:", out)  # the test fonts have no GPOS features

    def test_errors(self):
        cases = [
            (("--weight", "400"), 1, "only apply to variable fonts", "TestSans-Regular.otf"),
            (("--weight", "950"), 1, "outside the axis range", "TestSans[wght,wdth].ttf"),
            (("--weight", "bold"), 1, "invalid axis value", "TestSans[wght,wdth].ttf"),
            (("--weight", "400", "--axis", "wght=700"), 1, "given twice", "TestSans[wght,wdth].ttf"),
            (
                ("--weight", "400", "--weight", "700"),
                1,
                "--weight given twice; put all values in one list, e.g. --weight 400,700",
                "TestSans[wght,wdth].ttf",
            ),
            (("--slant", "-15,0"), 1, "font has no 'slnt' axis", "TestSans[wght,wdth].ttf"),
            (("--axis", "wdth"), 1, "TAG=VALUES", "TestSans[wght,wdth].ttf"),
            (("--formats", "pdf"), 1, "unknown format", "TestSans[wght,wdth].ttf"),
            (("--static", "400"), 2, "unrecognized arguments", "TestSans[wght,wdth].ttf"),
            (("-n", "X"), 2, "unrecognized arguments", "TestSans[wght,wdth].ttf"),
            (("--nam", "X"), 2, "unrecognized arguments", "TestSans[wght,wdth].ttf"),
            ((), 1, "missing.ttf: No such file or directory", "missing.ttf"),
            (("--jobs", "0"), 2, "at least 1", "TestSans[wght,wdth].ttf"),
            (("--axis", "XXXX=1", "--axis", "XXXX=2"), 1, "axis 'XXXX' given twice\n", "TestSans[wght,wdth].ttf"),
            (
                ("--width", "75", "--axis", "wdth=100"),
                1,
                "use either --width or --axis wdth=",
                "TestSans[wght,wdth].ttf",
            ),
            (("--info",), 1, "No such file or directory", "missing.ttf"),
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
