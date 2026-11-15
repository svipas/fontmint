# Architecture

How a font flows through fontmint, and where each decision is made. The one-line role of each module is in [AGENTS.md](../AGENTS.md#where-code-lives).

## Pipeline

```text
cli.run()                                   core (pure: bytes in → bytes out)
─────────                                   ─────────────────────────────────
read every input   ──bytes──▶  prepare(font_bytes, Options) ─▶ Prepared
                                 ├─ load (recalc=False: keep bboxes/timestamps)
                                 ├─ freeze_features      (features.py)
                                 ├─ rename_family        (naming.py)
                                 ├─ static input   → files = {path: same-format bytes}, jobs = []
                                 └─ variable input → files = variable output (default mode only)
                                                     jobs  = static + trimmed-variable Jobs
check output paths across all inputs (output_paths)
ProcessPoolExecutor ─ Job ─▶  build_job(Job) → {path: bytes}
                                 ├─ instantiateVariableFont(location)
                                 ├─ kind="variable" → TTF/WOFF2 of the trimmed font
                                 └─ kind="static"   → set_static_names, hinting (keep/strip or
                                                      ttfautohint), ttf_to_otf, WOFF2 (convert.py)
write every file at the end
```

The CLI writes nothing until every input is prepared and every job has succeeded, so a failure never leaves partial output. Library users get the same steps, run one after another, from `mint(font_bytes, options)`.

## Key types (`core.py`)

| Type       | Role                                                                                                                                                                                                            |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Options`  | What to build: `features`, `name`, `axes` (tag → spec), `style_name`, `formats` (`None` = all), native-step switches. Strings or lists/sets are accepted for `features` and `formats`.                          |
| `Prepared` | Result of `prepare`: `files` ready now, `jobs` still to run, `frozen` count, `warnings`, `family`.                                                                                                              |
| `Job`      | One output from a variable font. `kind` is `"static"` (every axis pinned) or `"variable"` (some axes trimmed). Carries the frozen + renamed variable font as `vf_bytes`, so it is self-contained and picklable. |
| `FontInfo` | Returned by `inspect()` for `--list-features`.                                                                                                                                                                  |

`FontmintError` (in `common.py`) is the only exception callers should expect. Errors from libraries inside a build job (e.g. ttfautohint) are converted to it; the CLI prints `fontmint: error: …` and exits with code 1.

## How variable input becomes jobs

- **No `axes`** (`_named_instance_jobs`): write the variable font itself, then one static `Job` per fvar **named instance**, using the designer's style name (`normalize_style`; repeated styles are built once).
- **With `axes`** (`_axis_jobs`): `axes.plan()` expands the specs into every combination of values. Each combination becomes:
  - a **static** `Job` if every axis in `axes` has a single value - other axes take their default value; the style comes from `naming.style_from_location()`;
  - a **variable** `Job` if any axis in `axes` has a range - other axes keep their full range; the file stem describes the limits (`-wght300-700`, `-Condensed`).
- Then come the checks: a range without the TTF or WOFF2 format is an error, `--style-name` is applied (it needs exactly one static job), static jobs from CFF2 variable fonts are an error, and so are duplicate output names.

## Module boundaries

| Module        | Must not                                                      |
| ------------- | ------------------------------------------------------------- |
| `common.py`   | depend on other fontmint modules                              |
| `features.py` | change outlines or layout tables (freezing only edits `cmap`) |
| `naming.py`   | touch name IDs 0, 7, 8–14                                     |
| `axes.py`     | know about output formats                                     |
| `convert.py`  | import native helpers at module level                         |
| `core.py`     | print, exit, or use the filesystem                            |
| `cli.py`      | contain font logic                                            |

## Native helpers

| Helper           | Used for                          | Switch                              |
| ---------------- | --------------------------------- | ----------------------------------- |
| `ttfautohint-py` | `*-hinted/` from unhinted sources | `--no-hint` / `Options(hint=False)` |
| `skia-pathops`   | overlap removal before CFF        | `Options(remove_overlaps=False)`    |
| `cffsubr`        | CFF subroutinization              | `Options(subroutinize=False)`       |

With all three off, a run imports none of them (tested in `test_core.NativeHelpersOptionalTest`) - the prerequisite for a possible Pyodide/browser build, where they can't run.

## Under the hood

What each step does to the font, and which library does it:

1. **Freeze** - [opentype-feature-freezer](https://github.com/twardoch/fonttools-opentype-feature-freezer) reads the GSUB lookups for the requested features and points the character map at the substituted glyphs. Only `cmap` changes; features with nothing to remap (ligatures, contextual) produce a warning.
2. **Rename** - the family is replaced in the name records that identify the font and in the CFF names of OTF fonts; notices are left alone (see [output-rules.md](output-rules.md#renaming-all-fonts)).
3. **Instance** - [fontTools](https://github.com/fonttools/fonttools)' `varLib.instancer` pins axes for static fonts or limits them for trimmed variable fonts. A range may exclude the axis default; fontTools then moves the default into the range. A hinted source's `cvar` is applied, so its hints stay correct for each instance.
4. **Hint** - sources with their own hinting keep it for `*-hinted/` and are stripped for `*-unhinted/`; unhinted sources go through [ttfautohint](https://freetype.org/ttfautohint/) via `ttfautohint-py` (bundled library, no system install).
5. **Convert to OTF** - overlapping contours are merged with [skia-pathops](https://github.com/fonttools/skia-pathops), because CFF has no overlap flag. Runs of quadratic curves become cubic curves with `Qu2CuPen` (max error 1 font unit, fontTools' default: a tighter value gained nothing measurable, and a looser one caused visible area differences on hairline accents). Left side bearings are recomputed from the new outlines, and the `post` italic angle and underline values are copied into the CFF top dict. Finally, [cffsubr](https://github.com/adobe-type-tools/cffsubr) subroutinizes the CFF table, which roughly halves its size. No CFF hints are added.
6. **WOFF2** - fontTools with Brotli; lossless.
