# fontmint

fontmint is a Python CLI and library for making your own builds of fonts. It freezes OpenType features (so `ss02` or `zero` become the default glyphs), renames the family, and exports variable fonts as variable + static TTF (hinted and unhinted), OTF and WOFF2 at any axis value.

You can think of fontmint as "take the font you like and make it yours" - without opening a font editor.

## What makes fontmint special?

People use fontmint on fonts they rely on every day, for their editor, their terminal and their website. Here are the things we can never compromise on.

### 1. We don't break fonts

Whatever fontmint writes must install and render correctly. Static input passes through untouched apart from the features you freeze or turn off and the new name: same format, original hinting kept, no extra files. Variable output only gets the same edits - never hinted, never outline-converted. When in doubt, change less.

### 2. We respect licenses

Most fonts people modify are under the SIL Open Font License. Renaming never touches copyright, trademark or license notices (name IDs 0, 7, 8–14). A renamed build must never pass itself off as the original.

### 3. Simple to run

One command, sensible defaults. Long options only, clear errors, no half-written output when something fails.

### 4. A pure core

The font logic is bytes in, bytes out. It never prints, exits or touches the filesystem, and its native helpers are optional. That keeps it usable as a library and leaves the door open for a browser build (Pyodide) - not planned yet, but not to be closed off by accident.

## How to approach changes

Prefer simple systems and software that feels obvious. Do not preserve complexity just because it already exists, and do not introduce machinery because it looks architecturally impressive. Understand the real constraint, then aim for the smallest change that makes the correct behavior unsurprising.

Channel both "measure twice, cut once" and "yagni". Fight scope creep. Honor the developer's intent in a minimal and realistic way.

The rest of this document helps you navigate the codebase and make changes effectively. Think of it less as hard rules and more as good defaults; the developer's preferences override anything here.

## A small glossary

- **you** means the agent reading this file and changing fontmint.
- **we** and **maintainers** mean the people building fontmint - who you are talking to now.
- **user** means the person running fontmint on their fonts.
- **static input** means a non-variable TTF, OTF, WOFF or WOFF2 file. It passes through.
- **variable input** means a font with an `fvar` table. It is the only input that produces static fonts, trimmed fonts and extra formats.
- **named instance** means a style the font's designer defined in `fvar` (e.g. "Condensed Bold"). Without axis options, fontmint builds one static font per named instance.
- **freeze** means remapping the character map so a GSUB substitution becomes the default glyph, then updating ligatures and context rules so they still work with the frozen glyphs.
- **trimmed variable font** means a variable font whose axes were limited by a range (`--weight 300:700`).
- **job** means one output built from a variable font, run in a worker process.

## The four ways to hurt yourself

1. **Renaming notices.** Replacing the family name everywhere also rewrites the copyright and trademark ("The Inter **Clear** Project Authors"). Rename only the name IDs in `naming.FAMILY_NAME_IDS` and ≥ 256.
2. **Native imports at module level.** `ttfautohint`, `skia-pathops` (`removeOverlaps`) and `cffsubr` are imported inside functions in `convert.py` only. A top-level import makes the whole core unusable where they don't exist.
3. **Side effects in the core.** `core.py` and everything below it never print, exit, read or write files. Raise `FontmintError`; `cli.py` turns it into a message.
4. **Writing as you go.** The CLI prepares every input, checks that no two inputs write the same file, builds every job, and only then writes. Keep it that way, or one bad font or failing job leaves a half-finished build behind.

## Where code lives

- `fontmint/core.py` - the pipeline: `Options` → `prepare()` → `Prepared` (files + jobs) → `build_job()`. Also `mint()` and `inspect()`.
- `fontmint/axes.py` - axis values (`400,700`, `300:700`, `all`) and their combinations.
- `fontmint/features.py` - listing, freezing and disabling features.
- `fontmint/naming.py` - family renaming, style names, name records, weight/width classes.
- `fontmint/convert.py` - TrueType → OTF and autohinting. The only module that uses native helpers.
- `fontmint/common.py` - `FontmintError`, `FORMATS`, loading/saving fonts.
- `fontmint/cli.py` - argparse, file I/O, parallel builds. Its module docstring is the `--help` epilog.
- `tests/` - `unittest` suite; `tests/fixtures.py` builds tiny fonts in code.
- `assets/` - the logo.

Dependency direction: `common` ← `features` / `naming` / `axes` / `convert` ← `core` ← `cli`. Nothing imports `cli`.

How a font flows through these modules: [docs/architecture.md](docs/architecture.md). Exactly what gets built, and how files and styles are named: [docs/output-rules.md](docs/output-rules.md).

## Setup and running

- `python3 -m venv .venv && .venv/bin/pip install -e .` sets up a development install.
- `.venv/bin/fontmint FONT --info` shows axes, named instances, features and languages.
- `.venv/bin/fontmint FONT --features ss01 --name "X" --output /tmp/x` runs the tool. Write test output outside the repo; `dist/` is gitignored but easy to forget.

## Verifying

- Run `.venv/bin/python -m unittest` after every change. It takes about two seconds.
- Behavior changes ship with focused tests in the matching `tests/test_<module>.py`. Extend an existing case where one fits before adding a new one.
- Bug fixes get a failing test first, then the fix.
- Build test fonts with `tests/fixtures.py`. Never commit binary font files.
- When refactoring, prove outputs didn't change by comparing font tables before and after: [docs/testing.md](docs/testing.md).
- For changes that touch real-world font structure (composites, overlaps, many lookups), also run a real family such as Inter once. The synthetic fixtures can't cover everything.

## Changing behavior

- **New option:** add it to `Options` in `core.py`, map it in `cli.py`, and document it in the README (_Options_ table and an example) and in the `cli.py` module docstring.
- **Different outputs:** update [docs/output-rules.md](docs/output-rules.md) and the README in the same change.
- **CLI:** long options only, `allow_abbrev=False`. Axis flags require a value (`--weight all`); an optional value would swallow a following font filename.
- **Jobs** run in worker processes, so `Job` must stay plain picklable data.

## Documentation

- `README.md` is for users and contributors: what fontmint does, how to install and use it, options, outputs.
- `docs/` holds decisions, constraints and traps that are hard to see from the code. Before adding a paragraph, ask what a maintainer would get wrong without it. If reading the code answers the question, leave it out.
- When a documented rule changes, rewrite or remove the old text instead of appending a new account.
- Format Markdown with `npx --yes oxfmt README.md AGENTS.md docs` (`--check` to verify without writing).

## Commits

- Never commit or push unless the developer explicitly asks.
- Plain-language commit titles that say what changed for the user: `fix: renaming no longer touches copyright notices`.
- Do not commit build output, test fonts or scratch files.

## Taste

- Python 3.10+, type hints, `from __future__ import annotations`, docstrings on public functions, lines up to about 120 characters. There is no linter config; match the surrounding code.
- Standard library first. Tests use `unittest`; don't add test or tooling dependencies.
- Default to no comment. Write one for a constraint, an external quirk or an invariant the code can't show.
- Errors are for the user: say what's wrong and how to fix it (`--weight expects …`, `add ttf or woff2 to formats`).

## Gotchas

- In argparse help strings, a literal `%` must be written `%%`, or `--help` crashes.
- fontTools re-serializes tables it loaded: `GSUB` bytes can change after freezing even where its content didn't. Compare tables with `toXML` when bytes differ.
- `Qu2CuPen(all_cubic=True)` raises `NotImplementedError` on contours without on-curve points (common after overlap removal). `ttf_to_otf` falls back to exact conversion for that glyph.
- Freezing changes `cmap`, so the font's other rules have to be updated, and only the ones that ran **before** the frozen feature (`rvrn` counts as first; nested lookups run at their caller's position). Updating a rule that ran after it creates behavior the original never had - e.g. an `fi` ligature in Recursive's monospaced italic. See `features._repair` and [docs/architecture.md](docs/architecture.md#under-the-hood).
- A frozen glyph that already has its own character (`²` for `sups`) must not be taught other rules; Private Use codes don't count, as fonts like Inter give every alternate one.
- Verify freezing changes against HarfBuzz: the frozen font with default settings must shape like the original with the feature on, also with other features on (e.g. `tnum`) and, for variable fonts, at several axis locations.
- One-word families ("Inter") make display and PostScript names look identical. Renaming decides by name ID, not by spaces alone.
- Quote file names with brackets (`'OpenSans[wdth,wght].ttf'`) in examples - zsh treats brackets as patterns. Don't quote real globs (`InterVariable*.ttf`), or the shell won't expand them.
- ttfautohint fails on fonts without Latin reference glyphs (icon fonts). `convert.autohint` turns that into a `FontmintError` pointing at `--no-hint`.
- A variable font can ship its own hinting. `*-hinted/` keeps it and `*-unhinted/` strips it (`convert.strip_hinting`); ttfautohint only runs for unhinted sources. A lone 7-byte `prep` + `gasp` (gftools' scan control, e.g. in JetBrains Mono) is **not** hinting - `convert.has_hinting` looks for `fpgm`, `cvt ` or glyph programs.
- Names read from a font (family, PostScript name) are untrusted: anything that becomes a path goes through `naming.safe_path_part`. `--name` is validated by `naming.check_name` instead.
- `common.load(check=True)` decompiles every table on a throwaway copy to catch damaged files, then returns a fresh lazy font - decompiled tables get re-serialized on save, which would change pass-through fonts.
