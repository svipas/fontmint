"""fontmint in the browser: the only module the page's workers call.

Values in and out are plain dicts, lists, strings and bytes, which Pyodide converts to
and from JavaScript. A worker can handle several input fonts, each by its file name:
prepare() keeps a font's plan, build() runs it. Progress goes to `report` as small dicts:

    {"type": "log", "font": "Inter.ttf", "text": "froze ss02: 412 characters remapped", "warning": False}
    {"type": "job", "font": "Inter.ttf", "done": 4, "total": 9, "style": "InterClear-Medium", "seconds": 5.1,
     "where": "opsz 14, wght 500", "location": {"opsz": 14, "wght": 500}}   # location: static fonts only
    {"type": "file", "path": "InterClear/ttf-unhinted/InterClear-Medium.ttf"}

The web never uses fontmint's native helpers: static fonts are unhinted, and static
OTF is left to the command line (it needs skia-pathops and cffsubr to be as good as
the CLI's). Tested on desktop Python in tests/test_web.py.
"""

from __future__ import annotations

import io
import time
import zipfile
from dataclasses import asdict, replace
from typing import Callable

from fontmint import FontmintError, Options, build_job, inspect
from fontmint import prepare as prepare_font
from fontmint.common import load
from fontmint.core import Prepared, check_clashes, output_paths
from fontmint.features import changed_characters

__all__ = ["describe", "prepare", "check_clashes", "build", "zip_files"]

Report = Callable[[dict], None]

_prepared: dict[str, Prepared] = {}  # file name → plan, for this worker's fonts


def describe(name: str, font_bytes: bytes) -> dict:
    """What the page shows about a dropped font: inspect() as a dict, plus whether it
    has CFF2 outlines (its variable font is written as OTF) and, per feature, the
    characters freezing it swaps (the preview marks them)."""
    data = bytes(font_bytes)
    try:
        info = asdict(inspect(data))
        font = load(data, check=False)
        info["cff2"] = "CFF2" in font
        info["changes"] = changed_characters(font, info["features"])
    except FontmintError as e:
        raise FontmintError(f"{name}: {e}") from e
    return info


def web_options(options: dict, variable: bool, cff2: bool) -> Options:
    """The page's options as core Options, with what the web can build: no hinting, and
    OTF only as the own format of a CFF2 variable font."""
    options = dict(options)
    if not variable:
        # Static input keeps its own format; the page shows no output options for it.
        options.pop("formats", None)
        options.pop("static", None)
    else:
        own = "otf" if cff2 else "ttf"
        formats = set(options.get("formats") or (own, "woff2"))
        if "otf" in formats and not cff2:
            raise FontmintError("static OTF fonts need the fontmint command line, which merges overlapping outlines "
                                "and compacts them; here, choose ttf or woff2")
        options["formats"] = formats
    options["hint"] = False
    return Options(**options)


def prepare(name: str, font_bytes: bytes, options: dict, report: Report) -> dict:
    """Freeze, rename and plan one font. Returns the paths it will produce (for
    check_clashes() across all inputs before anything is built), the number of jobs
    build() will run, and the output folder.

    `options["styles"]`, a list of {"axes": …, "style_name": …}, plans several builds of
    the font as one - the way to name more than one static font (375 as Regular and 675
    as Bold), which on the command line takes one run per style."""
    data = bytes(font_bytes)
    options = dict(options)
    styles = options.pop("styles", None) or [{}]
    try:
        font = load(data, check=False)
        all_opts = [web_options({**options, **style}, "fvar" in font, "CFF2" in font) for style in styles]
        prepared = _merge([prepare_font(data, opts) for opts in all_opts])
    except FontmintError as e:
        raise FontmintError(f"{name}: {e}") from e
    _prepared[name] = prepared
    opts = all_opts[0]  # the styles only differ in axes and style name, which aren't logged

    def log(text: str, warning: bool = False) -> None:
        report({"type": "log", "font": name, "text": text, "warning": warning})

    # The same lines as the CLI prints
    if opts.features:
        language = f" ({opts.language})" if opts.language else ""
        log(f"froze {opts.features}{language}: {prepared.frozen} characters remapped")
    if opts.disable:
        log(f"disabled {opts.disable}")
    if opts.line_height is not None:
        log(f"line height {opts.line_height:g}")
    if opts.letter_spacing:
        log(f"letter spacing {opts.letter_spacing:+g} em")
    if prepared.subset:
        log(f"subset {opts.subset}: kept {prepared.subset[0]} of {prepared.subset[1]} characters")
    for warning in prepared.warnings:
        log(f"warning: {warning}", warning=True)
    return {"paths": output_paths(prepared), "jobs": len(prepared.jobs), "folder": prepared.folder}


def _merge(plans: list[Prepared]) -> Prepared:
    """Several plans of one font (one per style) as one."""
    if len(plans) == 1:
        return plans[0]
    paths = [path for plan in plans for path in output_paths(plan)]
    if clashes := sorted({path for path in paths if paths.count(path) > 1}):
        raise FontmintError(f"two styles would both build {clashes[0].split('/')[-1]}: give each style its own "
                            "axis values and name")
    return replace(plans[0],
                   warnings=list(dict.fromkeys(warning for plan in plans for warning in plan.warnings)),
                   files={path: data for plan in plans for path, data in plan.files.items()},
                   jobs=[job for plan in plans for job in plan.jobs])


def build(name: str, report: Report) -> dict[str, bytes]:
    """Build every file of a prepared font, reporting each finished job."""
    prepared = _prepared.pop(name)
    files = dict(prepared.files)
    for done, job in enumerate(prepared.jobs, 1):
        started = time.perf_counter()
        try:
            files |= build_job(job)
        except Exception as e:  # FontmintError or a library error
            raise FontmintError(f"{name}: {job.stem}: {e}") from e
        event = {"type": "job", "font": name, "done": done, "total": len(prepared.jobs), "style": job.stem,
                 "seconds": round(time.perf_counter() - started, 1), "where": _where(job.location)}
        if job.kind == "static":
            event["location"] = dict(job.location)
        report(event)
    return files


def _where(location: dict) -> str:
    """Axis values as the log shows them: "wght 375" or, for a custom range, "wght 300–700"."""
    return ", ".join(f"{tag} {value[0]:g}–{value[1]:g}" if isinstance(value, tuple) else f"{tag} {value:g}"
                     for tag, value in location.items())


def zip_files(files: dict[str, bytes], report: Report) -> bytes:
    """All files in one zip, in the CLI's folder layout."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.writestr(path, bytes(files[path]))
            report({"type": "file", "path": path})
    return buffer.getvalue()
