"""fontmint pipeline - bytes in → bytes out.

Nothing here touches the filesystem, parses arguments, prints or exits, so it can
be used from the CLI, from other Python code, or in a browser (Pyodide).

Static fonts (TTF, OTF, WOFF, WOFF2) pass through: features are frozen and the
family renamed, nothing else changes - same format, hinting kept, no extra files.

Variable fonts produce:
  - the variable font itself (features frozen, renamed, otherwise unchanged)
    plus a static font for every named instance - when no axis options are given;
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
from .features import (
    FreezeResult,
    disable_features,
    freeze_features,
    list_features,
    parse_features,
    parse_tags,
)
from .naming import (
    WINDOWS_FAMILY_LIMIT,
    apply_style_name,
    axis_label,
    check_name,
    check_ps_length,
    legacy_names,
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


# Features many scripts need to show text correctly; turning them off gets a warning.
TEXT_FEATURES = {"ccmp", "locl", "mark", "mkmk", "rlig", "init", "medi", "fina", "isol", "rclt", "abvm", "blwm"}


@dataclass
class Options:
    """What to build.

    features:    features to freeze, "ss01,zero" or ["ss01", "zero"]; "cv47=14" picks the
                 14th alternate of a feature that offers several.
    disable:     features to turn off, e.g. "liga,calt" (GSUB or GPOS).
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

    features: str | list[str] | dict[str, int] = ""
    disable: str | list[str] = ""
    name: str = ""
    axes: dict[str, object] = field(default_factory=dict)
    style_name: str = ""
    formats: str | set[str] | None = None
    hint: bool = True
    remove_overlaps: bool = True
    subroutinize: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.features, dict):
            self.features = ",".join(f"{tag}={value}" for tag, value in self.features.items())
        elif not isinstance(self.features, str):
            self.features = ",".join(self.features or [])
        if not isinstance(self.disable, str):
            self.disable = ",".join(self.disable or [])
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
                raise FontmintError(f"no formats selected (choose from {', '.join(FORMATS)})")


@dataclass
class FontInfo:
    family: str
    variable: bool
    axes: list[tuple[str, float, float, float]]           # (tag, min, default, max)
    instances: list[tuple[str, dict[str, float]]]          # (style name, coordinates)
    features: list[str]                                    # substitution (GSUB) feature tags
    italic: bool
    positioning: list[str] = field(default_factory=list)  # positioning (GPOS) feature tags, e.g. kern


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
    """Family, axes, named instances and features of a font."""
    font = load(font_bytes)
    variable = is_variable(font)
    axes = [(a.axisTag, a.minValue, a.defaultValue, a.maxValue) for a in font["fvar"].axes] if variable else []
    instances = []
    if variable:
        for inst in font["fvar"].instances:
            instances.append((get_name(font, inst.subfamilyNameID) or "?", dict(inst.coordinates)))
    return FontInfo(family_name(font), variable, axes, instances, list_features(font), is_italic(font),
                    list_features(font, "GPOS"))



def prepare(font_bytes: bytes, options: Options) -> Prepared:
    """Freeze features and rename one font, and plan everything to build from it."""
    options.validate()
    spec = parse_features(options.features)
    disable = parse_tags(options.disable)
    if both := sorted(set(spec) & set(disable)):
        raise FontmintError(f"{', '.join(both)} can't be frozen and disabled at the same time")
    font = load(font_bytes, recalc=False)
    variable = is_variable(font)
    old_family = family_name(font)
    warnings: list[str] = []

    if disable:
        disable_features(font, disable)
        if needed := [t for t in disable if t in TEXT_FEATURES]:
            warnings.append(f"turning off {', '.join(needed)} can break text: these features place accents or "
                            "join and shape letters in many scripts")
    if options.name:
        if options.name in (old_family, old_family.removesuffix(" Variable")):
            warnings.append("--name is the original family name; the build will clash with the original font")
        warnings += rename_family(font, old_family, options.name)
        check_ps_length(get_name(font, 6) or "")
    elif variable or spec or disable:
        warnings.append("no --name given; the output keeps the original family name and will clash with the "
                        "original font (add --name to avoid this)")

    frozen = 0
    if spec:
        result = freeze_features(font, spec)
        frozen = result.remapped
        warnings += _freeze_warnings(options.features, result)

    if variable:
        return _prepare_variable_input(font, options, old_family, frozen, warnings)
    return _prepare_static_input(font, options, old_family, frozen, warnings)


def _freeze_warnings(features: str, result: FreezeResult) -> list[str]:
    warnings = []
    if result.remapped == 0 and result.outputs_changed == 0:
        warnings.append(f"'{features}' changed nothing: it only changes ligatures, or glyphs that depend on "
                        "neighboring characters, which can't be frozen (they can be turned off with --disable)")
    elif result.partial:
        warnings.append(f"{', '.join(result.partial)}: only the one-to-one swaps were frozen; the feature's other "
                        "rules (e.g. for accented letters, ligatures, or swaps that depend on neighboring characters) "
                        "can't be frozen, so some characters keep their original shape")
    if result.stale_rules:
        warnings.append(f"{result.stale_rules} group(s) of the font's rules can't be updated for the frozen glyphs, "
                        "so some ligatures and forms that depend on neighboring characters won't appear")
    return warnings


def _long_name_warning(family_names: list[str]) -> list[str]:
    longest = max(family_names, key=len, default="")
    if len(longest) <= WINDOWS_FAMILY_LIMIT:
        return []
    return [f"family names like '{longest}' are longer than {WINDOWS_FAMILY_LIMIT} characters, which some "
            "Windows apps cut off; a shorter --name avoids this"]


def _prepare_static_input(font, options, old_family, frozen, warnings) -> Prepared:
    """Static input passes through in its own format - nothing else is generated."""
    if options.axes:
        raise FontmintError("axis options (--weight, --width, …) only apply to variable fonts")
    if options.style_name:
        raise FontmintError("--style-name only applies to static fonts built from a variable font")
    if options.formats is not None:
        warnings.append("formats are ignored for static fonts; the output keeps the input format")
    family = options.name or old_family
    folder = safe_path_part(family)
    stem = safe_path_part(get_name(font, 6) or folder)
    if options.name:
        warnings += _long_name_warning([get_name(font, 1) or family])
    path = f"{folder}/{stem}.{extension(font)}"
    return Prepared(family, frozen, warnings, {path: to_bytes(font, font.flavor)}, [])


def _prepare_variable_input(font, options, old_family, frozen, warnings) -> Prepared:
    family = options.name or old_family.removesuffix(" Variable")
    folder = safe_path_part(family)
    formats = set(options.formats) if options.formats is not None else set(FORMATS)
    italic = is_italic(font)
    cff2 = "CFF2" in font
    vf_bytes = to_bytes(font)
    job_args = dict(vf_bytes=vf_bytes, family=family, formats=formats, hint=options.hint,
                    remove_overlaps=options.remove_overlaps, subroutinize=options.subroutinize)
    if options.axes:
        files, jobs = {}, _axis_jobs(font, options.axes, folder, italic, job_args)
    else:
        axes = ",".join(a.axisTag for a in font["fvar"].axes)
        stem = f"{folder}{'-Italic' if italic else ''}[{axes}]"
        files = _variable_files(vf_bytes, f"{folder}/variable/{stem}", formats, cff2)
        jobs = _named_instance_jobs(font, italic, job_args)

    own = "otf" if cff2 else "ttf"
    if not formats & {own, "woff2"}:
        hint = f"variable fonts are written as {own}/woff2 - add {own} or woff2 to --formats"
        if any(j.kind == "variable" for j in jobs):
            raise FontmintError(f"ranges make variable fonts, but {hint}")
        if not options.axes:
            warnings.append(f"the variable font is skipped: {hint}")

    statics = [j for j in jobs if j.kind == "static"]
    if options.style_name:
        if len(statics) != 1:
            raise FontmintError("--style-name only works when exactly one static font is built "
                                f"(this would build {len(statics)}; give each axis option a single value)")
        _restyle(statics[0], apply_style_name(options.style_name, italic))
    warnings += _long_name_warning([legacy_names(j.family, j.style)[0] for j in statics])
    if statics and cff2:
        raise FontmintError("static fonts from CFF2 (OTF) variable fonts aren't supported yet; "
                            "use the font's TrueType (.ttf) version if there is one")
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


def _variable_files(data: bytes, base: str, formats: set[str], cff2: bool) -> dict[str, bytes]:
    """Variable output from compiled font bytes: no hinting, no outline conversion -
    only lossless WOFF2."""
    files = {}
    own = "otf" if cff2 else "ttf"
    if own in formats:
        files[f"{base}.{own}"] = data
    if "woff2" in formats:
        files[f"{base}.woff2"] = to_bytes(load(data, recalc=False, check=False), "woff2")
    return files


def build_job(job: Job) -> dict[str, bytes]:
    """Run one job. Returns {relative path: bytes}."""
    font = instantiateVariableFont(load(job.vf_bytes, check=False), job.location, inplace=True)
    if job.kind == "variable":
        return _variable_files(to_bytes(font), f"{job.folder}/variable/{job.stem}", job.formats, "CFF2" in font)

    stem = set_static_names(font, job.family, job.style, job.weight_class, job.width_class)
    mark_monospaced(font)
    # Each output starts from these bytes: a font loaded from bytes copies the tables
    # it doesn't touch instead of compiling them again (GSUB/GPOS take seconds).
    data = to_bytes(font)
    unhinted = to_bytes(strip_hinting(load(data, check=False)))
    # A hinted source keeps the designer's hints (adjusted to the instance by the
    # instancer); ttfautohint is only used for sources without hinting.
    hinted = None
    if job.hint and {"ttf", "woff2"} & job.formats:
        hinted = data if has_hinting(font) else autohint(unhinted)

    files = {}
    if "ttf" in job.formats:
        files[f"{job.folder}/ttf-unhinted/{stem}.ttf"] = unhinted
        if hinted:
            files[f"{job.folder}/ttf-hinted/{stem}.ttf"] = hinted
    if "otf" in job.formats:
        otf = ttf_to_otf(load(unhinted, check=False), job.remove_overlaps, job.subroutinize)
        files[f"{job.folder}/otf/{stem}.otf"] = to_bytes(otf)
    if "woff2" in job.formats:
        files[f"{job.folder}/woff2-unhinted/{stem}.woff2"] = to_bytes(load(unhinted, check=False), "woff2")
        if hinted:
            files[f"{job.folder}/woff2-hinted/{stem}.woff2"] = to_bytes(load(hinted, check=False), "woff2")
    return files


def mark_monospaced(font: TTFont) -> None:
    """Mark a static font as monospaced when every character has the same width -
    zero-width marks and double-width glyphs (e.g. an ffi ligature) aside - as apps
    that only list monospaced fonts check this. A designer's own setting is never
    cleared."""
    widths = [font["hmtx"][g][0] for g in set(font.getBestCmap().values())]
    common = max(set(widths), key=widths.count, default=0)
    if common == 0 or not set(widths) <= {0, common, 2 * common}:
        return
    font["post"].isFixedPitch = 1
    panose = font["OS/2"].panose
    if panose.bFamilyType == 2:  # Latin text: bProportion 9 means monospaced
        panose.bProportion = 9


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
