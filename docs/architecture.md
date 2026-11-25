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
                                 └─ variable input → files = variable TTF/OTF with letter spacing (default mode only)
                                                     jobs  = its WOFF2 (first), static + custom-range Jobs
check_clashes(output_paths of every input)
ProcessPoolExecutor ─ Job ─▶  build_job(Job) → {path: bytes}
                                 ├─ kind="variable", no location → WOFF2 of vf_bytes as they are
                                 ├─ instantiateVariableFont(location)
                                 ├─ add_letter_spacing   (metrics.py)
                                 ├─ kind="variable" → TTF/WOFF2 of the custom-range font
                                 └─ kind="static"   → set_static_names, mark_monospaced, hinting
                                                      (keep/strip or ttfautohint), ttf_to_otf, WOFF2
report.render(every font's entry, files) ─▶ {folder/fontmint.txt: text}
write every file at the end, the reports last
```

The CLI writes nothing until every input is prepared and every job has succeeded, so a failure never leaves partial output. Library users get the same steps, run one after another, from `mint(font_bytes, options)`.

## Key types (`core.py`)

| Type       | Role                                                                                                                                                                                                                                                                                                           |
| ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Options`  | What to build: `features`, `language`, `disable`, `line_height`, `letter_spacing`, `subset`, `name`, `axes` (tag → spec), `style_name`, `formats` (`None` = all), native-step switches. Lists are accepted next to the command line's comma-separated strings (`features` also takes a dict, `formats` a set). |
| `Prepared` | Result of `prepare`: `files` ready now, `jobs` still to run, `frozen` count, `warnings`, `family`, `subset` (characters kept and before).                                                                                                                                                                      |
| `Job`      | One output from a variable font. `kind` is `"static"` (every axis pinned) or `"variable"` (some axes set to a custom range; none for the whole font). Carries the edited variable font as `vf_bytes`, so it is self-contained and picklable.                                                                   |
| `FontInfo` | Returned by `inspect()` for `--info`.                                                                                                                                                                                                                                                                          |

`FontmintError` (in `common.py`) is the error for bad input and options. The CLI prints it as `fontmint: error: …` and exits with code 1; it does the same for any other error a library raises inside a build job. Library users see such an error as it is - only ttfautohint's failure is turned into a `FontmintError`, as it has a known fix (`hint=False`).

## How variable input becomes jobs

- **No `axes`** (`_named_instance_jobs`): write the variable font itself (its WOFF2 is a `Job` too, run first: compressing it can take longer than a static font), then one static `Job` per fvar **named instance**, using the designer's style name (`normalize_style`; repeated styles are built once).
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
| `report.py`   | print, exit, use the filesystem or the clock; change a font  |
| `core.py`     | print, exit, or use the filesystem                           |
| `cli.py`      | contain font logic                                           |

## Native helpers

| Helper           | Used for                          | Switch                              |
| ---------------- | --------------------------------- | ----------------------------------- |
| `ttfautohint-py` | `*-hinted/` from unhinted sources | `--no-hint` / `Options(hint=False)` |
| `skia-pathops`   | overlap removal before CFF        | `Options(remove_overlaps=False)`    |
| `cffsubr`        | CFF subroutinization              | `Options(subroutinize=False)`       |

With all three off, a run imports none of them (tested in `test_core.NativeHelpersOptionalTest`). That is what lets the website run the core in the browser, where they can't run.

## Web version

`web/` is a static page on GitHub Pages that runs the same core in [Pyodide](https://pyodide.org) (CPython in WebAssembly), in Web Workers. There is no server: fonts are read, built and zipped in the browser.

```text
page (React, TanStack) ──postMessage──▶  worker.ts ─▶ pyodide/fontmint.ts ─▶ fontmint_web.py ─▶ core
  lib/options.ts: form → options dict       one Pyodide per worker              describe / prepare / check_clashes /
  store.ts: workers, progress, zip URL                                          run_job / zip_files
```

Decisions that aren't visible in the code:

- **Why Pyodide.** The core is already bytes in, bytes out, so the browser runs the code the CLI runs. A rewrite would have to re-verify freezing and its repairs; HarfBuzz in WebAssembly can subset and instance, but not freeze or rename.
- **How fontmint gets in.** Pyodide's own fontTools is too old for fontmint, and installing `fontmint` with its dependencies would make micropip fetch `fonttools[woff]` from PyPI, which wants a brotli and zopfli that have no WebAssembly builds. So Pyodide loads its own `micropip` and `brotli`, and a pinned pure-Python fontTools wheel and the fontmint wheel are installed from Pyodide's file system with `deps=False`. Zopfli isn't needed: WOFF2 uses only brotli. Every file is served by the site itself, checked against pinned hashes by `scripts/assets.ts`; the browser never asks a CDN or PyPI.
- **Never hinted, no static OTF.** ttfautohint-py and cffsubr run bundled programs through `subprocess`, and skia-pathops is a C extension Pyodide doesn't ship. For variable input, the glue always sets `hint=False`; it refuses `otf` unless the font has CFF2 outlines. Static OTF without overlap removal and subroutinization would be possible, but worse than the CLI's (unmerged overlaps, about twice the size), so the page points to the CLI instead. CFF2 variable fonts keep `otf`, as they never need a helper. A source's own hinting would survive without ttfautohint, but the page can't tell hinted sources apart yet.
- **Any worker can run any job.** `prepare()` returns a font's jobs as plain data (a pickled `Job` without its font, and the variable fonts the jobs share once), so a free worker takes the next job whichever font it belongs to (`lib/pool.ts`), as the CLI's process pool does. A build has at most one worker per job. Automatically it uses one fewer than the CPU cores, up to 8 (7 and 8 workers took the same time on an 8-core Mac), and 2 on phones and tablets; the user can pick another number. Browsers report neither cores nor memory reliably (Safari always says 4 or 8 cores, Brave random values), so neither limits that choice below 8. In Chromium, a worker added 85 to 230 MB, the most with a 20,000-glyph font. A build ends with its last job, as a small one is done before the other workers have started. Workers prepare the fonts, then one runs `core.check_clashes` over every input's output paths (the reason it moved out of `cli.py`), and only then do they build - the CLI's "check everything, then write" rule. One worker zips everything with Python's `zipfile`, in the CLI's folder layout. It also writes the report, from each font's `report.Entry`: plain data that `prepare()` returns.
- **Fonts are checked once.** `describe()` decompiles every table to find damage (over a second for Inter); `prepare()` gets the same bytes and skips it.
- **Fresh workers per build.** WebAssembly memory never shrinks, so every build ends its workers, and Cancel terminates them. The worker that read the fonts builds too; the others start only once it has Pyodide, so they load it from the browser cache instead of downloading 14.5 MB each. A first worker that can't load Pyodide, or any that crashes, fails the call and is replaced on the next one; others that can't load are left out of the build. Pyodide reports some failures (its `.wasm` file not arriving) outside the promise it returned, so `worker.ts` forwards unhandled errors as a `crash` message instead of leaving the page waiting.
- **The worker is a second entry point.** Bun's bundler doesn't follow `new Worker(...)`: `build.ts` builds `src/worker.ts` as `worker.js`, and `dev.ts` builds it on request. The glue module is bundled into it as text and written into Pyodide's file system.
- **The preview needs no Python.** The dropped font is loaded with the `FontFace` API and shown with CSS `font-feature-settings` and `font-variation-settings`. `describe()` lists, per feature, the characters freezing it swaps (`features.changed_characters`); the page marks them with the CSS Custom Highlight API, which paints over the text without splitting it into elements, so shaping is unchanged. After a build, the preview shows the built font itself, without CSS features.
- **Several custom styles are several plans.** `--style-name` names one static font per run, so the page's list of styles (375 as Regular, 675 as Bold) is sent as `styles`, and the glue plans the font once per style and merges the plans (`_merge`); the core is unchanged. The copied command line is one command per style for the same reason.
- **Checks run twice.** The page repeats fontmint's field checks so errors show as the user types (`formErrors()` in `lib/options.ts`); the core checks again when building, and its message is shown as it is. The two must change together.
- **Tests:** four layers, from the glue on desktop Python to the production build in real browsers: [testing.md](testing.md).
- **Its own releases.** The website has its own version (`web/package.json`), `web-v*` tags and changelog, so it can ship without a command-line release and the other way around. It deploys only on such a tag or by hand, never on a push to `main`, so the public page always runs released code. It runs the core at its commit, which may be ahead of the last `v*` release; `manifest.json` records both versions and the commit, and the footer shows the website's version, linked to its release notes, with the commit on hover.

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
