"""fontmint command line - arguments, files and parallel builds around fontmint.core.

Examples:
    # show axes, named instances, features and languages
    fontmint InterVariable.ttf --info

    # variable font + every named instance, in every format
    fontmint InterVariable*.ttf --features ss02 --name "Inter Clear"

    # static weights only, TTF + WOFF2
    fontmint InterVariable*.ttf --features ss02 --name "Inter Clear" \\
        --weight 400,500,600,700 --formats ttf,woff2

    # a weight between the standard ones, named "Regular"
    fontmint JetBrainsMono*.ttf --features zero --name "JetBrains Mono Clear" \\
        --weight 375 --style-name Regular

    # weights × widths (4 static fonts); quote file names with brackets
    fontmint 'OpenSans[wdth,wght].ttf' --name "Open Sans X" --weight 400,700 --width 75,100

    # a smaller variable font: weights 300–700 only
    fontmint InterVariable.ttf --name "Inter Light" --weight 300:700

    # a static font: freeze + rename only, same format, hinting kept
    fontmint FooFont-Regular.otf --features ss01 --name "Foo New"

    # a coding font without ligatures (JetBrains Mono keeps them in calt)
    fontmint JetBrainsMono*.ttf --disable calt --name "JetBrains Mono Flat"

    # more space between lines and letters
    fontmint JetBrainsMono*.ttf --name "JetBrains Mono Airy" --line-height 1.5 --letter-spacing 0.02

    # Romanian forms (ș ț with a comma below) as the default
    fontmint 'OpenSans[wdth,wght].ttf' --features locl --language ROM --name "Open Sans RO"
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from . import core
from .common import FORMATS, FontmintError

AXIS_FLAGS = {  # flag → (axis tag, help)
    "--weight": ("wght", "weight, e.g. 400,700 or 375 or 300:700"),
    "--width": ("wdth", "width in %%, e.g. 75,100 (75 = Condensed)"),
    "--slant": ("slnt", "slant angle in degrees, e.g. -10"),
    "--italic": ("ital", "italic axis, 0 or 1"),
    "--optical-size": ("opsz", "optical size, e.g. 32"),
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def read_font(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as e:
        raise FontmintError(e.strerror or str(e)) from e


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
    for rel, data in sorted(files.items()):
        path = out / rel
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as e:
            raise FontmintError(f"can't write {path}: {e.strerror}") from e
        log(f"  {rel}")


def collect_axes(args: argparse.Namespace) -> dict[str, str]:
    axes: dict[str, str] = {}
    for flag, (tag, _) in AXIS_FLAGS.items():
        value = getattr(args, flag.lstrip("-").replace("-", "_"))
        if value is not None:
            axes[tag] = value
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


def show_info(path: Path) -> None:
    try:
        info = core.inspect(read_font(path))
    except FontmintError as e:
        raise FontmintError(f"{path.name}: {e}") from e
    print(f"{path.name}\n  family:    {info.family}")
    if not info.variable:
        print("  type:      static font (features can be frozen; axis options don't apply)")
    else:
        axes = ", ".join(f"{t} {lo:g}–{hi:g} (default {d:g})" for t, lo, d, hi in info.axes)
        print(f"  axes:      {axes}")
        print(f"  instances: {', '.join(name for name, _ in info.instances) or '-'}")
    print(f"  features:  {' '.join(info.features) or '-'}")
    for i, (tag, name) in enumerate(info.feature_names.items()):
        print(f"  {'named:' if i == 0 else '':<10} {tag}  {name}")
    if info.positioning:
        print(f"  positioning: {' '.join(info.positioning)}")
    if info.languages:
        print(f"  languages: {' '.join(info.languages)}")
    print(f"  line height: {info.line_height:.2f}")


def package_version() -> str:
    try:
        return version("fontmint")
    except PackageNotFoundError:
        return "unknown"


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
    p.add_argument("fonts", nargs="+", type=Path, metavar="FONT",
                   help="font file(s): variable or static TTF/OTF/WOFF/WOFF2")
    p.add_argument("--version", action="version", version=f"%(prog)s {package_version()}")
    p.add_argument("--info", action="store_true",
                   help="show the font's axes, named instances, features and languages, then exit")
    p.add_argument("--features", default="", metavar="TAGS",
                   help="features to make the default (freeze), e.g. ss02,zero; for a feature with several "
                        "alternates, add a number: cv47=2 picks the second")
    p.add_argument("--language", default="", metavar="TAG",
                   help="freeze the forms the font has for a language, e.g. --features locl --language ROM for "
                        "Romanian ș ț with a comma below (--info shows the font's languages)")
    p.add_argument("--disable", default="", metavar="TAGS",
                   help="features to turn off, e.g. calt,liga for no ligatures (--info shows which a font has)")
    p.add_argument("--line-height", type=float, default=None, metavar="N",
                   help="line spacing as a multiple of the font size, like CSS line-height, e.g. 1.4 "
                        "(--info shows the current value)")
    p.add_argument("--letter-spacing", type=float, default=0, metavar="EM",
                   help="extra space after each character as a fraction of the font size, like CSS "
                        "letter-spacing in em, e.g. 0.05 (negative values tighten)")
    p.add_argument("--name", default="", metavar="NAME",
                   help='new family name, e.g. "Inter Clear" (recommended, so your build doesn\'t clash with '
                        'the original)')

    g = p.add_argument_group(
        "axes (variable fonts)",
        "Each takes single values (static fonts), MIN:MAX ranges (a smaller variable font),\n"
        "comma-separated lists of both, or 'all' (the values of the font's named instances,\n"
        "the styles its designer defined). With several axes, every combination is built.\n"
        "Without any axis option: the variable font plus a static font per named instance.",
    )
    for flag, (tag, help_text) in AXIS_FLAGS.items():
        g.add_argument(flag, default=None, metavar="VALUES", help=f"{help_text} [{tag}]")
    g.add_argument("--axis", action="append", default=[], metavar="TAG=VALUES",
                   help="any other axis by its tag, e.g. --axis MONO=1 (repeatable)")
    g.add_argument("--style-name", default="", metavar="NAME",
                   help="style name when exactly one static font is built, e.g. --weight 375 --style-name Regular")

    o = p.add_argument_group("output")
    o.add_argument("--formats", default=None, metavar="LIST",
                   help=f"formats to build from variable fonts, any of {','.join(FORMATS)} (default: all); "
                        "ttf and woff2 give hinted and unhinted static fonts. Static input keeps its format")
    o.add_argument("--no-hint", action="store_true",
                   help="don't build hinted static fonts (needed for fonts without Latin letters, e.g. icon fonts)")
    o.add_argument("--output", default="dist", metavar="DIR", help="output directory (default: ./dist)")
    o.add_argument("--jobs", type=positive_int, default=os.cpu_count() or 1, metavar="N",
                   help="number of fonts to build in parallel (default: number of CPUs)")
    return p


def run(args: argparse.Namespace) -> None:
    if args.info:
        for path in args.fonts:
            show_info(path)
        return

    options = core.Options(
        features=args.features,
        language=args.language,
        disable=args.disable,
        line_height=args.line_height,
        letter_spacing=args.letter_spacing,
        name=args.name,
        axes=collect_axes(args),
        style_name=args.style_name,
        formats=args.formats,
        hint=not args.no_hint,
    )
    out = Path(args.output)
    check_writable(out)

    # Prepare and build everything before writing, so a failure never leaves a
    # half-finished build behind.
    prepared_fonts: list[tuple[Path, core.Prepared]] = []
    for path in args.fonts:
        try:
            prepared_fonts.append((path, core.prepare(read_font(path), options)))
        except FontmintError as e:
            raise FontmintError(f"{path.name}: {e}") from e

    paths = Counter(p for _, prepared in prepared_fonts for p in core.output_paths(prepared))
    if clashes := sorted(p for p, n in paths.items() if n > 1):
        folder, name = clashes[0].split("/")[0], clashes[0].split("/")[-1]
        raise FontmintError(f"two inputs would both write {name} into {folder}/: the same font was given twice, "
                            "or different families got the same --name (build them separately, with different "
                            "names)")

    for path, prepared in prepared_fonts:
        log(path.name)
        if (out / prepared.folder).is_dir() and any((out / prepared.folder).iterdir()):
            log(f"  warning: {out / prepared.folder} already exists; files from earlier runs are kept unless this run "
                "replaces them")
        if options.features:
            language = f" ({options.language})" if options.language else ""
            log(f"  froze {options.features}{language}: {prepared.frozen} characters remapped")
        if options.disable:
            log(f"  disabled {options.disable}")
        if options.line_height is not None:
            log(f"  line height {options.line_height:g}")
        if options.letter_spacing:
            log(f"  letter spacing {options.letter_spacing:+g} em")
        for w in prepared.warnings:
            log(f"  warning: {w}")

    files: dict[str, bytes] = {}
    for _, prepared in prepared_fonts:
        files |= prepared.files
    jobs = [(path, job) for path, prepared in prepared_fonts for job in prepared.jobs]
    if jobs:
        workers = max(1, min(args.jobs, len(jobs)))
        log(f"building {len(jobs)} font(s) with {workers} worker(s)…")
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(core.build_job, job): (path, job) for path, job in jobs}
            for fut in as_completed(futures):
                path, job = futures[fut]
                try:
                    files |= fut.result()
                except Exception as e:  # FontmintError or a library error inside a worker
                    pool.shutdown(wait=False, cancel_futures=True)  # don't start the remaining jobs
                    raise FontmintError(f"{path.name}: {job.stem}: {e}") from e

    log(f"writing to {out}/")
    write_files(files, out)
    log(f"done: {len(files)} file(s)")


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run(args)
    except FontmintError as e:
        parser.exit(1, f"fontmint: error: {e}\n")
    except KeyboardInterrupt:
        parser.exit(130, "fontmint: interrupted\n")


if __name__ == "__main__":
    main()
