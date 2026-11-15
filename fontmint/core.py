"""fontmint pipeline — bytes in → bytes out.

Nothing here touches the filesystem, parses arguments, prints or exits, so it can
be used from the CLI, from other Python code, or in a browser (Pyodide).

Static fonts (TTF, OTF, WOFF, WOFF2) pass through: features are frozen and the
family renamed, nothing else changes — same format, hinting kept, no extra files.

Variable fonts give:
  - the variable font itself (features frozen, renamed, otherwise unchanged)
    plus a static font for every named instance — when no axis options are given;
  - otherwise exactly what the axis options ask for: pinned values → static fonts,
    ranges → trimmed variable fonts.

    from fontmint import Options, mint

    files = mint(open("InterVariable.ttf", "rb").read(),
                 Options(features="ss02", name="Inter Clear"))
    # {"InterClear/variable/InterClear[opsz,wght].ttf": b"...", ...}
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

from . import axes as axes_mod
from .common import FORMATS, FontmintError, extension, family_name, get_name, is_italic, is_variable, load, to_bytes
from .convert import autohint, has_hinting, strip_hinting, ttf_to_otf
from .features import freeze_features, list_features
from .naming import (
    apply_style_name,
    axis_label,
    check_name,
    check_ps_length,
    normalize_style,
    ps_name,
    rename_family,
    safe_path_part,
    set_static_names,
    style_from_location,
    weight_name,
    width_class,
    width_name,
)


@dataclass
class Options:
    """What to build.

    features:    features to freeze, "ss01,zero" or ["ss01", "zero"].
    name:        new family name.
    axes:        axis tag → values, e.g. {"wght": "400,700", "wdth": [75, (75, 100)]}.
                 Values pin (static fonts), MIN:MAX ranges trim (variable fonts),
                 "all" = every value used by the font's named instances.
                 Empty → variable font + every named instance.
    style_name:  style name when exactly one static font is built (375 → "Regular").
    formats:     subset of FORMATS for variable input, "ttf,woff2" or a set (None = all).
                 ttf/woff2 give hinted + unhinted statics. Ignored for static input.
    hint / remove_overlaps / subroutinize:
                 native steps for statics built from variable fonts; disable where
                 ttfautohint, skia-pathops or cffsubr can't run.
    """

    features: str | list[str] = ""
    name: str = ""
    axes: dict[str, object] = field(default_factory=dict)
    style_name: str = ""
    formats: str | set[str] | None = None
    hint: bool = True
    remove_overlaps: bool = True
    subroutinize: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.features, str):
            self.features = ",".join(self.features or [])
        self.name = " ".join(self.name.split())
        self.style_name = " ".join(self.style_name.split())
        if isinstance(self.formats, str):
            self.formats = {f.strip() for f in self.formats.split(",") if f.strip()}

    def validate(self) -> None:
        if self.name:
            check_name(self.name, "--name")
        if self.style_name:
            check_name(self.style_name, "--style-name")
        if self.formats is not None:
            if bad := set(self.formats) - set(FORMATS):
                raise FontmintError(f"unknown format(s): {', '.join(sorted(bad))} (choose from {', '.join(FORMATS)})")
            if not self.formats:
                raise FontmintError("no formats selected")


@dataclass
class FontInfo:
    family: str
    variable: bool
    axes: list[tuple[str, float, float, float]]           # (tag, min, default, max)
    instances: list[tuple[str, dict[str, float]]]          # (style name, coordinates)
    features: list[str]                                    # GSUB feature tags
    italic: bool


@dataclass
class Job:
    """One output built from a variable font. Picklable, so it can run in a
    worker process. kind="static" pins every axis; kind="variable" trims axes."""

    kind: str
    vf_bytes: bytes
    family: str
    stem: str                                  # file name without extension
    location: dict[str, float | tuple[float, float]]
    style: str = ""
    weight_class: int = 400
    width_class: int | None = None
    formats: set[str] = field(default_factory=lambda: set(FORMATS))
    hint: bool = True
    remove_overlaps: bool = True
    subroutinize: bool = True

    @property
    def folder(self) -> str:
        return safe_path_part(self.family)


@dataclass
class Prepared:
    """A frozen + renamed font: files that are ready now, and jobs still to run."""

    family: str
    frozen: int                        # characters remapped by features
    warnings: list[str]
    files: dict[str, bytes]
    jobs: list[Job]

    @property
    def folder(self) -> str:
        return safe_path_part(self.family)



def inspect(font_bytes: bytes) -> FontInfo:
    """Family, axes, named instances and GSUB features of a font."""
    font = load(font_bytes)
    variable = is_variable(font)
    axes = [(a.axisTag, a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes] if variable else []
    instances = []
    if variable:
        for inst in font["fvar"].instances:
            instances.append((get_name(font, inst.subfamilyNameID) or "?", dict(inst.coordinates)))
    return FontInfo(family_name(font), variable, axes, instances, list_features(font), is_italic(font))



def prepare(font_bytes: bytes, options: Options) -> Prepared:
    """Freeze features and rename one font, and plan everything to build from it."""
    options.validate()
    font = load(font_bytes, recalc=False)
    variable = is_variable(font)
    old_family = family_name(font)
    warnings: list[str] = []

    frozen = 0
    if options.features:
        frozen = freeze_features(font, options.features)
        if frozen == 0:
            warnings.append(f"'{options.features}' changed no characters: only single and alternate "
                            "substitutions (ssXX, cvXX, zero, …) can be frozen")
    if options.name:
        if options.name in (old_family, old_family.removesuffix(" Variable")):
            warnings.append("--name is the original family name; the build will clash with the original")
        rename_family(font, old_family, options.name)
        check_ps_length(get_name(font, 6) or "")
    elif variable or options.features:
        warnings.append("no --name given; the output keeps the original family name and will clash with it")

    if variable:
        return _prepare_variable_input(font, options, old_family, frozen, warnings)
    return _prepare_static_input(font, options, old_family, frozen, warnings)


def _prepare_static_input(font, options, old_family, frozen, warnings) -> Prepared:
    """Static input passes through in its own format — nothing else is generated."""
    if options.axes:
        raise FontmintError("axis options (--weight, --width, …) only apply to variable fonts")
    if options.style_name:
        raise FontmintError("--style-name only applies to static fonts built from a variable font")
    if options.formats is not None:
        warnings.append("formats are ignored for static fonts; the output keeps the input format")
    family = options.name or old_family
    folder = safe_path_part(family)
    stem = safe_path_part(get_name(font, 6) or folder)
    path = f"{folder}/{stem}.{extension(font)}"
    return Prepared(family, frozen, warnings, {path: to_bytes(font, font.flavor)}, [])


def _prepare_variable_input(font, options, old_family, frozen, warnings) -> Prepared:
    family = options.name or old_family.removesuffix(" Variable")
    folder = safe_path_part(family)
    formats = set(options.formats) if options.formats is not None else set(FORMATS)
    italic = is_italic(font)
    cff2 = "CFF2" in font
    job_args = dict(vf_bytes=to_bytes(font), family=family, formats=formats, hint=options.hint,
                    remove_overlaps=options.remove_overlaps, subroutinize=options.subroutinize)

    if options.axes:
        files, jobs = {}, _axis_jobs(font, options.axes, folder, italic, job_args)
    else:
        axes = ",".join(a.axisTag for a in font["fvar"].axes)
        stem = f"{folder}{'-Italic' if italic else ''}[{axes}]"
        files = _variable_files(font, f"{folder}/variable/{stem}", formats, cff2)
        jobs = _named_instance_jobs(font, italic, job_args)

    own = "otf" if cff2 else "ttf"
    if not formats & {own, "woff2"}:
        hint = f"variable fonts are written as {own}/woff2 — add {own} or woff2 to formats"
        if any(j.kind == "variable" for j in jobs):
            raise FontmintError(f"ranges make variable fonts, but {hint}")
        if not options.axes:
            warnings.append(f"the variable font is skipped: {hint}")

    statics = [j for j in jobs if j.kind == "static"]
    if options.style_name:
        if len(statics) != 1:
            raise FontmintError("--style-name only works when exactly one static font is built "
                                f"(this would build {len(statics)})")
        _restyle(statics[0], apply_style_name(options.style_name, italic))
    if statics and cff2:
        raise FontmintError("static fonts from CFF2 (OTF) variable fonts aren't supported yet")
    stems = [j.stem for j in jobs]
    if dupes := sorted({s for s in stems if stems.count(s) > 1}):
        raise FontmintError(f"several outputs would get the same name: {', '.join(dupes)}")
    return Prepared(family, frozen, warnings, files, jobs)


def _named_instance_jobs(font: TTFont, italic: bool, job_args: dict) -> list[Job]:
    """One static job per fvar named instance, named as the designer named it."""
    defaults = {a.axisTag: a.defaultValue for a in font["fvar"].axes}
    jobs, seen = [], set()
    for inst in font["fvar"].instances:
        loc = defaults | dict(inst.coordinates)
        designer_name = get_name(font, inst.subfamilyNameID)
        style = normalize_style(designer_name) if designer_name else style_from_location(loc, set(), italic)
        if style not in seen:
            seen.add(style)
            jobs.append(_static_job(loc, style, job_args))
    return jobs


def _axis_jobs(font: TTFont, specs: dict, folder: str, italic: bool, job_args: dict) -> list[Job]:
    """Jobs for --weight/--width/…: pinned combinations → static, ranges → trimmed variable."""
    fvar_axes = [a.axisTag for a in font["fvar"].axes]
    defaults = {a.axisTag: a.defaultValue for a in font["fvar"].axes}
    plan = axes_mod.plan(font, specs)
    jobs = []
    for combo in plan.combos:
        if axes_mod.is_static(combo):
            loc = defaults | combo
            jobs.append(_static_job(loc, style_from_location(loc, plan.labeled, italic), job_args))
        else:
            remaining = [t for t in fvar_axes if not (t in combo and not isinstance(combo[t], tuple))]
            limits = "-".join(_describe(t, v) for t, v in combo.items())
            stem = f"{folder}{'-Italic' if italic else ''}-{limits}[{','.join(remaining)}]"
            jobs.append(Job(kind="variable", stem=stem, location=dict(combo), **job_args))
    return jobs


def _static_job(loc: dict[str, float], style: str, job_args: dict) -> Job:
    job = Job(kind="static", stem="", location=loc,
              weight_class=round(loc.get("wght", 400)),
              width_class=width_class(loc["wdth"]) if "wdth" in loc else None, **job_args)
    _restyle(job, style)
    return job


def _restyle(job: Job, style: str) -> None:
    job.style = style
    job.stem = ps_name(job.family, style)


def _describe(tag: str, v) -> str:
    """File-name fragment for a trimmed variable font, e.g. 'wght300-700', 'Condensed'."""
    if isinstance(v, tuple):
        return f"{tag}{v[0]:g}-{v[1]:g}"
    if tag == "wght":
        return weight_name(v)
    if tag == "wdth":
        return width_name(v) or "Normal"
    if tag == "ital":
        return "Italic" if v >= 0.5 else "Upright"
    return axis_label(tag, v)


def _variable_files(font: TTFont, base: str, formats: set[str], cff2: bool) -> dict[str, bytes]:
    """Variable output: no hinting, no outline conversion — only lossless WOFF2."""
    files = {}
    own = "otf" if cff2 else "ttf"
    if own in formats:
        files[f"{base}.{own}"] = to_bytes(font)
    if "woff2" in formats:
        files[f"{base}.woff2"] = to_bytes(font, "woff2")
    return files



def build_job(job: Job) -> dict[str, bytes]:
    """Run one job. Returns {relative path: bytes}."""
    font = instantiateVariableFont(load(job.vf_bytes, check=False), job.location)
    if job.kind == "variable":
        return _variable_files(font, f"{job.folder}/variable/{job.stem}", job.formats, "CFF2" in font)

    stem = set_static_names(font, job.family, job.style, job.weight_class, job.width_class)
    # A hinted source keeps the designer's hints (adjusted to the instance by the
    # instancer); ttfautohint is only used for sources without hinting.
    wants_hinted = job.hint and bool({"ttf", "woff2"} & job.formats)
    unhinted = strip_hinting(font)
    if has_hinting(font):
        hinted = font if wants_hinted else None
    else:
        hinted = autohint(unhinted) if wants_hinted else None

    files = {}
    if "ttf" in job.formats:
        files[f"{job.folder}/ttf-unhinted/{stem}.ttf"] = to_bytes(unhinted)
        if hinted:
            files[f"{job.folder}/ttf-hinted/{stem}.ttf"] = to_bytes(hinted)
    if "otf" in job.formats:
        files[f"{job.folder}/otf/{stem}.otf"] = to_bytes(ttf_to_otf(unhinted, job.remove_overlaps, job.subroutinize))
    if "woff2" in job.formats:
        files[f"{job.folder}/woff2-unhinted/{stem}.woff2"] = to_bytes(unhinted, "woff2")
        if hinted:
            files[f"{job.folder}/woff2-hinted/{stem}.woff2"] = to_bytes(hinted, "woff2")
    return files


def output_paths(prepared: Prepared) -> list[str]:
    """Every path `prepared` will produce (before building), for collision checks."""
    paths = list(prepared.files)
    for job in prepared.jobs:
        kinds = ["variable"] if job.kind == "variable" else ["static"]
        paths += [f"{job.folder}/{kind}/{job.stem}" for kind in kinds]
    return paths


def mint(font_bytes: bytes, options: Options | None = None) -> dict[str, bytes]:
    """Build everything for one font, sequentially. Returns {relative path: bytes},
    e.g. "InterClear/otf/InterClear-Bold.otf"."""
    prepared = prepare(font_bytes, options or Options())
    files = dict(prepared.files)
    for job in prepared.jobs:
        files |= build_job(job)
    return files
