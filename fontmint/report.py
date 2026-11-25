"""What a build changed, as text: the lines it logs, and the fontmint.txt next to its fonts."""

from __future__ import annotations

import re
import shlex
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import cast

from . import axes as axes_mod
from .common import FORMATS, family_name, get_name, is_variable, load
from .core import Options, Prepared
from .features import feature_names, parse_features, parse_tags
from .metrics import line_height

FILE_NAME = "fontmint.txt"
LABEL_WIDTH = 16
MISREAD_START = ("-", "=")  # argparse takes "-…" for an option, zsh expands "=…"


@dataclass
class Entry:
    """One input font's part of a report. Plain data, so fonts prepared apart (in the
    website's workers) can share one report."""

    font: str
    note: str  # not in `changes`, so fonts with the same changes can share a section
    source: str  # e.g. "Inter 4.001"
    family: str
    folder: str
    changes: list[str]
    commands: list[str]  # only the arguments
    warnings: list[str]


def log_lines(options: Options, prepared: Prepared) -> list[str]:
    """What a build logs about one font's changes."""
    lines = []
    if options.features:
        language = f" ({options.language})" if options.language else ""
        lines.append(f"froze {options.features}{language}: {prepared.frozen} characters remapped")
    if options.disable:
        lines.append(f"disabled {options.disable}")
    if options.line_height is not None:
        lines.append(f"line height {options.line_height:g}")
    if options.letter_spacing:
        lines.append(f"letter spacing {options.letter_spacing:+g} em")
    if prepared.subset:
        lines.append(f"subset {options.subset}: kept {prepared.subset[0]} of {prepared.subset[1]} characters")
    return lines


def make_entry(name: str, font_bytes: bytes, options: Sequence[Options], prepared: Prepared) -> Entry:
    """The report's part about the font in the file `name`. `options` holds one item, or one
    per style when `prepared` merges several builds (they differ only in axis values and
    style name)."""
    font = load(font_bytes, check=False)
    variable = is_variable(font)
    family = family_name(font)
    version = re.search(r"(?:^|version)[\s:]*(\d+(?:\.\d+)*)", get_name(font, 5) or "", re.IGNORECASE)
    statics = any(job.kind == "static" for job in prepared.jobs)
    first = options[0]

    changes: list[str] = []

    def add(label: str, *values: str) -> None:
        for i, value in enumerate(values):
            changes.append(f"{'' if i else label:<{LABEL_WIDTH}}{value}")

    if first.name and first.name != family:
        add("Family name", f"{first.name} (was {family})")
    features, disable, subset = (cast(str, t) for t in (first.features, first.disable, first.subset))
    names = feature_names(font) if features or disable else {}
    frozen = parse_features(features)
    add("Made default", *(_feature(tag if n == 1 else f"{tag}={n}", names.get(tag)) for tag, n in frozen.items()))
    if first.language:
        add("Language", first.language)
    add("Turned off", *(_feature(tag, names.get(tag)) for tag in parse_tags(disable)))
    if first.line_height is not None:
        add("Line height", f"{_number(first.line_height)} (was {line_height(font):.2f})")
    if first.letter_spacing:
        add("Letter spacing", f"{'+' if first.letter_spacing > 0 else ''}{_number(first.letter_spacing)} em")
    note = ""
    if prepared.subset:
        kept, before = prepared.subset
        note = f"(kept {kept:,} of {before:,} characters)"
        add("Characters", ", ".join(parse_tags(subset)))
    if variable:
        add("Styles", *(_style(o) for o in options if o.axes or o.style_name))
        if formats := _formats(first):
            add("Formats", ", ".join(formats))
        if not first.static:
            add("Static fonts", "none")
        elif statics and not first.hint:
            add("Hinting", "no hinted static fonts")

    return Entry(
        font=name,
        note=note,
        source=f"{family} {version[1]}" if version else family,
        family=prepared.family,
        folder=prepared.folder,
        changes=changes,
        commands=[_arguments(o) for o in options],
        warnings=prepared.warnings,
    )


def render(entries: Sequence[Entry], paths: Iterable[str], made_with: str) -> dict[str, bytes]:
    """A report for each output folder: {"InterClear/fontmint.txt": b"…"}. `paths` are the
    files that were built, `made_with` says what built them."""
    folders: dict[str, list[Entry]] = {}
    for entry in entries:
        folders.setdefault(entry.folder, []).append(entry)
    files = sorted(paths)
    return {
        f"{folder}/{FILE_NAME}": _text(
            group, [p.removeprefix(f"{folder}/") for p in files if p.startswith(f"{folder}/")], made_with
        )
        for folder, group in folders.items()
    }


def _text(entries: list[Entry], files: list[str], made_with: str) -> bytes:
    lines = [
        entries[0].family,
        "",
        f"{'Made from':<{LABEL_WIDTH}}{', '.join(dict.fromkeys(e.source for e in entries))}",
        f"{'Made with':<{LABEL_WIDTH}}{made_with}",
        "",
        "This is a custom build, not the original font.",
    ]

    sections: dict[tuple[str, ...], list[str]] = {}
    commands: dict[str, list[str]] = {}
    warnings: dict[str, list[str]] = {}
    for entry in entries:
        sections.setdefault(tuple(entry.changes), []).append(f"{entry.font} {entry.note}".rstrip())
        for arguments in entry.commands:
            commands.setdefault(arguments, []).append(entry.font)
        for warning in entry.warnings:
            warnings.setdefault(warning, []).append(entry.font)

    lines += ["", "", "Changes"]
    for changes, fonts in sections.items():
        lines += ["", *(f"  {font}" for font in fonts), *(f"    {change}" for change in changes or ["No changes"])]
    lines += ["", "", "The same build on the command line", ""]
    for arguments, fonts in commands.items():
        names = _join(f"./{font}" if font.startswith(MISREAD_START) else font for font in fonts)
        lines.append(f"  fontmint {names} {arguments}".rstrip())
    if warnings:
        lines += ["", "", "Warnings", ""]
        for warning, fonts in warnings.items():
            which = "" if len(fonts) == len(entries) else f"{', '.join(fonts)}: "
            lines.append(f"  - {which}{warning}")
    lines += ["", "", "Files", "", *(f"  {path}" for path in files), ""]
    return "\n".join(map(_printable, lines)).encode()


def _printable(line: str) -> str:
    """Drops line breaks and control characters, so an untrusted name can't fake other lines."""
    return "".join(c for c in line if c.isprintable() or unicodedata.category(c) == "Zs")


def _arguments(options: Options) -> str:
    arguments: list[str] = []

    def add(flag: str, value: str) -> None:
        if value.startswith(MISREAD_START):
            arguments.append(f"{flag}={value}")
        elif value:
            arguments.extend([flag, value])

    add("--features", cast(str, options.features))
    add("--language", options.language)
    add("--disable", cast(str, options.disable))
    if options.line_height is not None:
        add("--line-height", _number(options.line_height))
    if options.letter_spacing:
        add("--letter-spacing", _number(options.letter_spacing))
    add("--subset", cast(str, options.subset))
    add("--name", options.name)
    for tag, spec in options.axes.items():
        if flag := axes_mod.FLAGS.get(tag):
            add(flag, _axis_values(spec))
        else:
            add("--axis", f"{tag}={_axis_values(spec)}")
    add("--style-name", options.style_name)
    add("--formats", ",".join(_formats(options)))
    if not options.static:
        arguments.append("--no-static")
    elif not options.hint:
        arguments.append("--no-hint")
    return _join(arguments)


def _join(words: Iterable[str]) -> str:
    """Quoted for a shell: in double quotes where those are safe, as cmd.exe knows no others."""
    return " ".join(
        word if word == (quoted := shlex.quote(word)) else quoted if set(word) & set('"$`\\!') else f'"{word}"'
        for word in words
    )


def _feature(tag: str, name: str | None) -> str:
    return f"{tag}  {name}" if name else tag


def _style(options: Options) -> str:
    """Axis values in words: 'weight 375, width 75 as "Regular"'."""
    axes = ", ".join(
        f"{axes_mod.FLAGS.get(tag, tag).removeprefix('--').replace('-', ' ')} "
        + _axis_values(spec).replace(":", "–").replace(",", ", ")
        for tag, spec in options.axes.items()
    )
    name = f'as "{options.style_name}"' if options.style_name else ""
    return " ".join(filter(None, [axes, name]))


def _axis_values(spec: object) -> str:
    """As the command line takes them: "400,700" or "300:700"."""
    return ",".join(
        item if isinstance(item, str) else ":".join(map(_number, item if isinstance(item, tuple) else (item,)))
        for item in axes_mod.parse_spec(spec)
    )


def _formats(options: Options) -> list[str]:
    """The formats asked for; empty when that's all of them."""
    formats = [f for f in FORMATS if f in (options.formats or ())]
    return [] if len(formats) == len(FORMATS) else formats


def _number(value: float) -> str:
    return f"{value:.10g}"
