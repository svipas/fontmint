"""fontmint command line - arguments, files and parallel builds around fontmint.core.

Examples:
    # show axes, named instances, features and languages
    fontmint InterVariable.ttf --info

    # variable font + every named instance, in every format
    fontmint InterVariable*.ttf --features ss02 --name "Inter Clear"

    # only the variable font
    fontmint InterVariable*.ttf --features ss02 --name "Inter Clear" --no-static

    # static weights only, TTF + WOFF2
    fontmint InterVariable*.ttf --features ss02 --name "Inter Clear" \\
        --weight 400,500,600,700 --formats ttf,woff2

    # a weight between the standard ones, named "Regular"
    fontmint JetBrainsMono*.ttf --features zero --name "JetBrains Mono Zero" \\
        --weight 375 --style-name Regular

    # weights × widths (4 static fonts); quote file names with brackets
    fontmint 'OpenSans[wdth,wght].ttf' --name "Open Sans Custom" --weight 400,700 --width 75,100

    # a smaller variable font: weights 300–700 only
    fontmint InterVariable.ttf --name "Inter Text" --weight 300:700

    # a static font: freeze + rename only, same format, hinting kept
    fontmint FiraCode-Regular.ttf --features zero --name "Fira Code Zero"

    # a coding font without ligatures (JetBrains Mono keeps them in calt)
    fontmint JetBrainsMono*.ttf --disable calt --name "JetBrains Mono Flat"

    # more space between lines and letters
    fontmint JetBrainsMono*.ttf --name "JetBrains Mono Airy" --line-height 1.5 --letter-spacing 0.02

    # smaller web fonts with only Latin characters
    fontmint InterVariable.ttf --name "Inter Web" --subset latin,latin-ext --formats woff2

    # Romanian forms (ș ț with a comma below) as the default
    fontmint 'OpenSans[wdth,wght].ttf' --features locl --language ROM --name "Open Sans RO"
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from . import __version__, core, report
from .axes import FLAGS
from .common import FORMATS, FontmintError

AXIS_HELP = {
    "wght": "weight, e.g. 400,700 or 375 or 300:700",
    "wdth": "width in %%, e.g. 75,100 (75 = Condensed)",
    "slnt": "slant angle in degrees, e.g. -10",
    "ital": "italic axis, 0 or 1",
    "opsz": "optical size, e.g. 32",
}
AXIS_FLAGS = {flag: (tag, AXIS_HELP[tag]) for tag, flag in FLAGS.items()}
FONT_SUFFIXES = {".ttf", ".otf", ".woff", ".woff2", ".ttc", ".otc"}
FONT_SIGNATURES = {b"\0\1\0\0", b"OTTO", b"true", b"wOFF", b"wOF2", b"ttcf"}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def read_fonts(paths: list[Path]) -> list[tuple[Path, bytes]]:
    """The fonts among `paths`: `folder/*` also gives licenses, readmes and folders. A file
    named like a font always counts: a damaged one has to fail, or a family would be built
    without it."""
    fonts = []
    for path in paths:
        if os.path.isdir(path):
            log(f"skipped {path.name or path}: a folder")
            continue
        try:
            data = path.read_bytes()
        except OSError as e:
            raise FontmintError(f"{path.name}: {e.strerror or e}") from e
        if path.suffix.lower() in FONT_SUFFIXES or data[:4] in FONT_SIGNATURES:
            fonts.append((path, data))
        else:
            log(f"skipped {path.name}: not a font")
    if not fonts:
        raise FontmintError("no fonts to read; give TTF, OTF or WOFF2 files (folders aren't searched)")
    return fonts


def positive_int(value: str) -> int:
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError(f"expected a whole number of at least 1, got '{value}'")
    return int(value)


def check_writable(path: Path) -> None:
    """Fail early if `path` can't become a directory we can write into."""
    if path.exists() and not path.is_dir():
        raise FontmintError(f"can't write to {path}: it exists and is not a folder")
    existing = next(p for p in (path, *path.parents) if p.exists())
    if not existing.is_dir() or not os.access(existing, os.W_OK | os.X_OK):
        raise FontmintError(f"can't write to {path}: no write permission for {existing}")


def write_files(files: dict[str, bytes], out: Path) -> None:
    # Check every destination folder first, so a permission problem can't stop
    # the run halfway through writing.
    for folder in sorted({(out / rel).parent for rel in files}):
        check_writable(folder)
    for rel, data in files.items():
        path = out / rel
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except (OSError, ValueError) as e:  # ValueError: a path the OS rejects, e.g. with a null byte
            raise FontmintError(f"can't write {path}: {getattr(e, 'strerror', None) or e}") from e
        log(f"  {rel}")


def collect_axes(args: argparse.Namespace) -> dict[str, str]:
    axes: dict[str, str] = {}
    for flag, (tag, _) in AXIS_FLAGS.items():
        values = getattr(args, flag.lstrip("-").replace("-", "_"))
        if len(values) > 1:
            raise FontmintError(f"{flag} given twice; put all values in one list, e.g. {flag} {','.join(values)}")
        if values:
            axes[tag] = values[0]
    for item in args.axis:
        tag, sep, spec = item.partition("=")
        if not sep or not tag or not spec:
            raise FontmintError(f"--axis expects TAG=VALUES, e.g. --axis MONO=1, got '{item}'")
        if tag in axes:
            flag = next((f for f, (t, _) in AXIS_FLAGS.items() if t == tag), None)
            hint = f" (use either {flag} or --axis {tag}=…)" if flag else ""
            raise FontmintError(f"axis '{tag}' given twice{hint}")
        axes[tag] = spec
    return axes


def show_info(path: Path, data: bytes) -> None:
    try:
        info = core.inspect(data)
    except FontmintError as e:
        raise FontmintError(f"{path.name}: {e}") from e

    def row(label: str, value: str) -> None:
        print(f"  {label:<12} {value}")

    print(path.name)
    row("family:", info.family)
    if not info.variable:
        row("type:", "static font (features can be frozen; axis options don't apply)")
    else:
        row("axes:", ", ".join(f"{t} {lo:g}–{hi:g} (default {d:g})" for t, lo, d, hi in info.axes))
        row("instances:", ", ".join(name for name, _ in info.instances) or "-")
    row("features:", " ".join(info.features) or "-")
    for i, (tag, name) in enumerate(info.feature_names.items()):
        row("" if i else "named:", f"{tag}  {name}")
    if info.positioning:
        row("positioning:", " ".join(info.positioning))
    if info.languages:
        row("languages:", " ".join(info.languages))
    row("line height:", f"{info.line_height:.2f}")


def build_parser() -> argparse.ArgumentParser:
    examples = (__doc__ or "").partition("Examples:")[2]
    p = argparse.ArgumentParser(
        prog="fontmint",
        description="Make OpenType features (stylistic sets, slashed zero, ...) the default glyphs and\n"
        "rename the font family. Variable fonts are also exported as variable and static\n"
        "TTF (hinted and unhinted), OTF and WOFF2.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Examples:{examples}" if examples else None,
        allow_abbrev=False,
    )
    p.add_argument("fonts", nargs="+", type=Path, metavar="FONT", help="font file(s): variable or static TTF/OTF/WOFF2")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--info", action="store_true", help="show the font's axes, named instances, features, languages and line height"
    )
    p.add_argument(
        "--features",
        default="",
        metavar="TAGS",
        help="features to make the default (freeze), e.g. ss02,zero; for a feature with several "
        "alternates, add a number: cv47=2 picks the second",
    )
    p.add_argument(
        "--language",
        default="",
        metavar="TAG",
        help="freeze the forms the font has for a language, e.g. --features locl --language ROM for "
        "Romanian ș ț with a comma below (--info shows the font's languages)",
    )
    p.add_argument(
        "--disable",
        default="",
        metavar="TAGS",
        help="features to turn off, e.g. calt,liga for no ligatures (--info shows which a font has)",
    )
    p.add_argument(
        "--line-height",
        type=float,
        default=None,
        metavar="N",
        help="line spacing as a multiple of the font size, like CSS line-height, e.g. 1.4; "
        "0.5 to 3 (--info shows the current value)",
    )
    p.add_argument(
        "--letter-spacing",
        type=float,
        default=0,
        metavar="EM",
        help="extra space after each character as a fraction of the font size, like CSS "
        "letter-spacing in em, e.g. 0.05; -0.5 to 1 (negative values tighten)",
    )
    p.add_argument(
        "--subset",
        default="",
        metavar="LIST",
        help="keep only these characters, for smaller web fonts: latin, latin-ext, cyrillic, "
        "cyrillic-ext, greek, vietnamese, or ranges like U+2190-21FF (comma-separated). "
        "Only latin has digits, punctuation and the space: add it to the others",
    )
    p.add_argument(
        "--name",
        default="",
        metavar="NAME",
        help='new family name, e.g. "Inter Clear" (recommended, so your build doesn\'t clash with the original)',
    )

    g = p.add_argument_group(
        "axes (variable fonts)",
        "Each takes single values (static fonts), MIN:MAX ranges (a smaller variable font),\n"
        "comma-separated lists of both, or 'all' (the values of the font's named instances,\n"
        "the styles its designer defined). With several axes, every combination is built.\n"
        "Without any axis option: the variable font plus a static font per named instance.",
    )
    for flag, (tag, help_text) in AXIS_FLAGS.items():
        g.add_argument(flag, action="append", default=[], metavar="VALUES", help=f"{help_text} [{tag}]")
    g.add_argument(
        "--axis",
        action="append",
        default=[],
        metavar="TAG=VALUES",
        help="any other axis by its tag, e.g. --axis MONO=1 (repeatable)",
    )
    g.add_argument(
        "--style-name",
        default="",
        metavar="NAME",
        help="style name when exactly one static font is built, e.g. --weight 375 --style-name Regular",
    )

    o = p.add_argument_group("output")
    o.add_argument(
        "--formats",
        default=None,
        metavar="LIST",
        help=f"formats to build from variable fonts, any of {','.join(FORMATS)} (default: all); "
        "ttf and woff2 give hinted and unhinted static fonts. Static input keeps its format",
    )
    o.add_argument(
        "--no-static", action="store_true", help="build only the variable font from variable input, no static fonts"
    )
    o.add_argument(
        "--no-hint",
        action="store_true",
        help="don't build hinted static fonts (needed for fonts without Latin letters, e.g. icon fonts)",
    )
    o.add_argument("--output", default="dist", metavar="DIR", help="output directory (default: ./dist)")
    o.add_argument(
        "--jobs",
        type=positive_int,
        default=os.cpu_count() or 1,
        metavar="N",
        help="number of fonts to build in parallel (default: number of CPUs)",
    )
    return p


def run(args: argparse.Namespace) -> None:
    fonts = read_fonts(args.fonts)
    if args.info:
        for path, data in fonts:
            show_info(path, data)
        return

    options = core.Options(
        features=args.features,
        language=args.language,
        disable=args.disable,
        line_height=args.line_height,
        letter_spacing=args.letter_spacing,
        subset=args.subset,
        name=args.name,
        axes=collect_axes(args),
        style_name=args.style_name,
        formats=args.formats,
        static=not args.no_static,
        hint=not args.no_hint,
    )
    out = Path(args.output)
    check_writable(out)

    # Prepare and build everything before writing, so a failure never leaves a
    # half-finished build behind.
    prepared_fonts: list[tuple[Path, core.Prepared]] = []
    entries: list[report.Entry] = []
    for path, data in fonts:
        try:
            prepared = core.prepare(data, options)
        except FontmintError as e:
            raise FontmintError(f"{path.name}: {e}") from e
        prepared_fonts.append((path, prepared))
        entries.append(report.make_entry(path.name, data, [options], prepared))

    core.check_clashes([core.output_paths(prepared) for _, prepared in prepared_fonts])

    for path, prepared in prepared_fonts:
        log(path.name)
        if _has_files(out / prepared.folder):
            log(
                f"  warning: {out / prepared.folder} already exists; files from earlier runs are kept unless this run "
                "replaces them"
            )
        for line in report.log_lines(options, prepared):
            log(f"  {line}")
        for w in prepared.warnings:
            log(f"  warning: {w}")

    files: dict[str, bytes] = {}
    for _, prepared in prepared_fonts:
        files |= prepared.files
    jobs = [(path, job) for path, prepared in prepared_fonts for job in prepared.jobs]
    if jobs:
        workers = min(args.jobs, len(jobs), 61)  # Windows can't run more than 61 worker processes
        log(f"building {len(jobs)} font(s) with {workers} worker(s)…")
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(core.build_job, job): (path, job) for path, job in jobs}
            for fut in as_completed(futures):
                path, job = futures[fut]
                try:
                    files |= fut.result()
                except Exception as e:  # FontmintError or a library error inside a worker
                    pool.shutdown(wait=False, cancel_futures=True)
                    raise FontmintError(f"{path.name}: {job.stem}: {str(e) or type(e).__name__}") from e

    made_with = f"fontmint {__version__} (https://github.com/svipas/fontmint)"
    reports = report.render(entries, files, made_with)
    files = dict(sorted(files.items())) | reports

    log(f"writing to {out}/")
    write_files(files, out)
    log(f"done: {len(files)} file(s)")


def _has_files(folder: Path) -> bool:
    try:
        return folder.is_dir() and any(folder.iterdir())
    except OSError:  # not readable; writing reports it
        return False


def _join_negative_axis_values(argv: list[str]) -> list[str]:
    """`--slant -15,0` → `--slant=-15,0`: before Python 3.14, argparse takes a value
    like `-15,0` or `-15:0` for an unknown option (a plain `-15` is fine)."""
    joined: list[str] = []
    for arg in argv:
        if joined and joined[-1] in AXIS_FLAGS and re.match(r"-[\d.]", arg):
            joined[-1] += f"={arg}"
        else:
            joined.append(arg)
    return joined


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):  # font and file names can hold characters a terminal can't show
        if reconfigure := getattr(stream, "reconfigure", None):
            reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(_join_negative_axis_values(sys.argv[1:] if argv is None else argv))
    try:
        run(args)
    except FontmintError as e:
        parser.exit(1, f"fontmint: error: {e}\n")
    except KeyboardInterrupt:
        parser.exit(130, "fontmint: interrupted\n")


if __name__ == "__main__":
    main()
