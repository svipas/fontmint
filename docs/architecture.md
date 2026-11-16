# Architecture

How a font flows through fontmint, and where each decision is made. The one-line role of each module is in [AGENTS.md](../AGENTS.md#where-code-lives).

## Pipeline

```text
cli.run()                                   core (pure: bytes in → bytes out)
─────────                                   ─────────────────────────────────
read every input   ──bytes──▶  prepare(font_bytes, Options) ─▶ Prepared
                                 ├─ load (recalc=False: keep bboxes/timestamps)
                                 ├─ disable_features     (features.py)
                                 ├─ rename_family        (naming.py)
                                 ├─ freeze_features      (features.py)
                                 ├─ set_line_height      (metrics.py)
                                 ├─ subset_font          (subset.py)
                                 ├─ static input   → letter spacing; files = {path: same-format bytes}, jobs = []
                                 └─ variable input → files = variable output with letter spacing (default mode only)
                                                     jobs  = static + custom-range Jobs
check output paths across all inputs (output_paths)
ProcessPoolExecutor ─ Job ─▶  build_job(Job) → {path: bytes}
                                 ├─ instantiateVariableFont(location)
                                 ├─ add_letter_spacing   (metrics.py)
                                 ├─ kind="variable" → TTF/WOFF2 of the custom-range font
                                 └─ kind="static"   → set_static_names, mark_monospaced, hinting
                                                      (keep/strip or ttfautohint), ttf_to_otf, WOFF2
write every file at the end
```

The CLI writes nothing until every input is prepared and every job has succeeded, so a failure never leaves partial output. Library users get the same steps, run one after another, from `mint(font_bytes, options)`.

## Key types (`core.py`)

| Type       | Role                                                                                                                                                                                                                                                                                                           |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Options`  | What to build: `features`, `language`, `disable`, `line_height`, `letter_spacing`, `subset`, `name`, `axes` (tag → spec), `style_name`, `formats` (`None` = all), native-step switches. Lists are accepted next to the command line's comma-separated strings (`features` also takes a dict, `formats` a set). |
| `Prepared` | Result of `prepare`: `files` ready now, `jobs` still to run, `frozen` count, `warnings`, `family`, `subset` (characters kept and before).                                                                                                                                                                      |
| `Job`      | One output from a variable font. `kind` is `"static"` (every axis pinned) or `"variable"` (some axes set to a custom range). Carries the edited variable font as `vf_bytes`, so it is self-contained and picklable.                                                                                            |
| `FontInfo` | Returned by `inspect()` for `--info`.                                                                                                                                                                                                                                                                          |

`FontmintError` (in `common.py`) is the error for bad input and options. The CLI prints it as `fontmint: error: …` and exits with code 1; it does the same for any other error a library raises inside a build job. Library users see such an error as it is - only ttfautohint's failure is turned into a `FontmintError`, as it has a known fix (`hint=False`).

## How variable input becomes jobs

- **No `axes`** (`_named_instance_jobs`): write the variable font itself, then one static `Job` per fvar **named instance**, using the designer's style name (`normalize_style`; repeated styles are built once).
- **With `axes`** (`_axis_jobs`): `axes.plan()` expands the specs into every combination of values. Each combination becomes:
  - a **static** `Job` if every axis in `axes` has a single value - other axes take their default value; the style comes from `naming.style_from_location()`;
  - a **variable** `Job` if any axis in `axes` has a range - other axes keep their full range; the file stem describes the limits (`-wght300-700`, `-Condensed`).
- Then come the checks: a range without the TTF or WOFF2 format is an error, `--style-name` is applied (it needs exactly one static job), static jobs from CFF2 variable fonts are an error (the default mode drops them with a warning instead), and so are duplicate output names.

## Module boundaries

| Module        | Must not                                                     |
| ------------- | ------------------------------------------------------------ |
| `common.py`   | depend on other fontmint modules                             |
| `features.py` | change outlines; it edits only `cmap` and GSUB/GPOS lookups  |
| `naming.py`   | touch name IDs 0, 7, 8–14                                    |
| `metrics.py`  | move outlines; it edits only line metrics and advance widths |
| `subset.py`   | drop names or hinting, or features that still have glyphs    |
| `axes.py`     | know about output formats                                    |
| `convert.py`  | import native helpers at module level                        |
| `core.py`     | print, exit, or use the filesystem                           |
| `cli.py`      | contain font logic                                           |

## Native helpers

| Helper           | Used for                          | Switch                              |
| ---------------- | --------------------------------- | ----------------------------------- |
| `ttfautohint-py` | `*-hinted/` from unhinted sources | `--no-hint` / `Options(hint=False)` |
| `skia-pathops`   | overlap removal before CFF        | `Options(remove_overlaps=False)`    |
| `cffsubr`        | CFF subroutinization              | `Options(subroutinize=False)`       |

With all three off, a run imports none of them (tested in `test_core.NativeHelpersOptionalTest`) - the prerequisite for a possible Pyodide/browser build, where they can't run.

## Under the hood

What each step does to the font, and which library does it:

1. **Disable** - `--disable` empties the lookup lists of the named features (GSUB and GPOS, feature variations included). The feature records stay, so no index shifts.
2. **Rename** - the family is replaced in the name records that identify the font and in the CFF names of OTF fonts; notices are left alone (see [output-rules.md](output-rules.md#renaming-all-fonts)).
3. **Freeze** - fontmint's freezer (`features.py`) collects the single (type 1) and alternate (type 3) lookups of the requested features, plus the one-glyph entries of multiple substitutions (type 2), and points the character map at what they produce. Features come from the default language system of each script, or from `--language`'s in the scripts that have that language (a feature that only exists for some languages asks for `--language` instead of quietly picking one). It follows how text engines run lookups: each lookup once, `rvrn` (and its feature-variation lookups) first, the rest in lookup-list order; lookups that context rules call run at their caller's position. `cv47=2` picks the second alternate. Old Mac format 0 subtables keep entries whose new glyph ID wouldn't fit in one byte.

   Then the font's other rules are made to behave as in the original with the feature on. Only rules that ran **before** a frozen lookup are touched (rules after it already saw the frozen glyphs). The principle: where such a rule saw a glyph in the original, it now sees what the frozen lookups after it turn that glyph into - whether the glyph comes from the character map or from an earlier rule. So:
   - their output glyphs are replaced by what the frozen feature turns them into, since it's now always on - e.g. a ligature JetBrains Mono builds in `calt` gets its `cv15` form, and Recursive's `rvrn` italic forms get `ss07`'s;
   - they learn each frozen glyph where they knew the old one: substitutions map it the same way, ligatures get a copy with the frozen components right after the original (the first match wins, so the font's order is kept), and context rules list it next to the old glyph (formats 2/3 and reverse chaining in coverages and classes; format 1 gets a copy of each rule right after the original, keeping priority).

   A frozen glyph that already has a character of its own (`²` for `sups`; Private Use codes don't count) isn't taught other rules, as text with that character would change too. Rules that can't be updated are counted (`FreezeResult.stale_rules`) and reported. Known gaps, all rare and not detected: a lookup used both before and after the frozen feature is treated as before; a frozen glyph that a class-based context rule already puts in another class keeps that class; lookup flags (e.g. "ignore marks") aren't considered when reading a lookup's substitutions.

   A frozen feature's lookups that the cmap can't hold (one-to-many, ligatures, context) are added to `calt`, or `liga` if a script has no `calt` (`FreezeResult.moved`). Both are on by default but usually off when an editor turns off ligatures. A lookup keeps its place in the lookup list, so it runs as in the original with the feature on; that holds only where engines apply all features in one pass, so this is limited to scripts shaped that way (Latin, Greek, Cyrillic, Armenian, Georgian, Hebrew), and a `calt` that a script like Arabic shares is left alone. Lookups that call an alternate lookup aren't moved for `cv47=2`, as apps would pick the first alternate. Features whose leftovers can't be moved are reported as partly frozen. Because the variable font itself is repaired, its static instances need no separate step.

4. **Line height** (`metrics.py`) - measured like CSS, in multiples of the font size. The change is split equally above and below and written to `hhea` and the OS/2 typo values (with "use typo metrics" set, raising OS/2 version 2/3 to 4, which has the same fields) with no line gap. `usWin*` only grows, since Windows clips glyphs outside it; old Windows apps that take their line height from `usWin*` therefore don't get a smaller one, and OS/2 versions 0/1 can't carry the "use typo metrics" bit at all. `MVAR` entries for those values and `VDMX` (line metrics per pixel size) are dropped.
5. **Subset** (`subset.py`) - fontTools' subsetter keeps the requested characters and every glyph they can reach through features. Its defaults are made for web fonts and would drop name IDs above 6 (license notices included), the stylistic sets and character variants, the `.notdef` outline and glyph names; fontmint turns all of these back on. It runs after freezing, so features already frozen into the character map count as reachable. A feature whose glyphs can no longer be reached (e.g. Inter's `cv05`, already part of a frozen `ss02`) is dropped with its lookups and its name. Tables fontTools can't subset (bitmaps, Apple's `morx`, …) are dropped, as they would point at the wrong glyphs, and a warning names them; Mac character maps are dropped too.

   Any edit also drops `DSIG`: the signature was made for the original file.

6. **Letter spacing** (`metrics.py`) - also like CSS. It widens every glyph with a width and leaves zero-width ones (accents) alone; outlines don't move, so GPOS kerning and anchors stay correct (an accent's offset shrinks by exactly the amount its base widened). In a monospaced font, double-width glyphs get twice the space, so they still fill two cells. Which glyphs have a width (or a double one) can depend on the axis values - Recursive's fraction slash is zero-width only in its proportional styles - so static and custom-range fonts get their spacing after instancing (`Job.letter_spacing`); only the full variable font decides at its default location. `hdmx` and `LTSH` hold per-size widths and are dropped. CFF charstrings store each width again and are kept in sync: a stated width is the charstring's first number, one left to the font's default width is added in front, and if a subroutine holds it the font is desubroutinized first.
7. **Instance** - [fontTools](https://github.com/fonttools/fonttools)' `varLib.instancer` pins axes for static fonts or narrows them for custom-range variable fonts. A range may exclude the axis default; fontTools then moves the default into the range. A hinted source's `cvar` is applied, so its hints stay correct for each instance.
8. **Hint** - sources with their own hinting keep it for `*-hinted/` and are stripped for `*-unhinted/`; unhinted sources go through [ttfautohint](https://freetype.org/ttfautohint/) via `ttfautohint-py` (bundled library, no system install).
9. **Convert to OTF** - the OTF starts from the unhinted TTF's compiled outlines, so both formats have the same rounded coordinates. Overlapping contours are merged with [skia-pathops](https://github.com/fonttools/skia-pathops), because CFF has no overlap flag. Runs of quadratic curves become cubic curves with `Qu2CuPen` (max error 1 font unit, fontTools' default: a tighter value gained nothing measurable, and a looser one caused visible area differences on hairline accents). Left side bearings are recomputed from the new outlines, and the `post` italic angle and underline values are copied into the CFF top dict. Finally, [cffsubr](https://github.com/adobe-type-tools/cffsubr) subroutinizes the CFF table, which roughly halves its size. No CFF hints are added.
10. **WOFF2** - fontTools with Brotli; lossless.
