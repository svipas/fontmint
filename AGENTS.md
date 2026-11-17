# fontmint

fontmint is a Python CLI and library for making your own builds of fonts. It freezes OpenType features (so `ss02` or `zero` become the default glyphs), renames the family, and exports variable fonts as variable + static TTF (hinted and unhinted), OTF and WOFF2 at any axis value.

You can think of fontmint as "take the font you like and make it yours" - without opening a font editor.

The same core also runs in the browser: [svipas.github.io/fontmint](https://svipas.github.io/fontmint/) runs it with Pyodide (Python in WebAssembly), so fonts never leave the user's computer. That page lives in `web/`.

## What makes fontmint special?

People use fontmint on fonts they rely on every day, for their editor, their terminal and their website. Here are the things we can never compromise on.

### 1. We don't break fonts

Whatever fontmint writes must install and render correctly. Static input passes through untouched apart from what you ask for (frozen or disabled features, the new name, line height, letter spacing and a subset): same format, original hinting kept, no extra files. Variable output only gets the same edits - never hinted, never outline-converted. When in doubt, change less.

### 2. We respect licenses

Most fonts people modify are under the SIL Open Font License. Renaming never touches copyright, trademark or license notices (name IDs 0, 7, 8–14). A renamed build must never pass itself off as the original.

### 3. Simple to run

One command, sensible defaults. Long options only, clear errors, no half-written output when something fails.

### 4. A pure core

The font logic is bytes in, bytes out. It never prints, exits or touches the filesystem, and its native helpers are optional. That keeps it usable as a library and lets the website run the same code in the browser, where none of the native helpers exist.

## How to approach changes

Prefer simple systems and software that feels obvious. Do not preserve complexity just because it already exists, and do not introduce machinery because it looks architecturally impressive. Understand the real constraint, then aim for the smallest change that makes the correct behavior unsurprising.

Channel both "measure twice, cut once" and "yagni". Fight scope creep. Honor the developer's intent in a minimal and realistic way.

The rest of this document helps you navigate the codebase and make changes effectively. Think of it less as hard rules and more as good defaults; the developer's preferences override anything here.

## A small glossary

- **you** means the agent reading this file and changing fontmint.
- **we** and **maintainers** mean the people building fontmint - who you are talking to now.
- **user** means the person running fontmint on their fonts.
- **static input** means a non-variable TTF, OTF or WOFF2 file. It passes through.
- **variable input** means a font with an `fvar` table. It is the only input that produces static fonts, custom-range variable fonts and extra formats.
- **named instance** means a style the font's designer defined in `fvar` (e.g. "Condensed Bold"). Without axis options, fontmint builds one static font per named instance.
- **freeze** means remapping the character map so a GSUB substitution becomes the default glyph, then updating the font's other rules (ligatures, context rules, …) so they still work with the frozen glyphs. Rules the character map can't hold are added to `calt` (or `liga`).
- **custom-range variable font** means a variable font whose axes were narrowed to a range (`--weight 300:700`).
- **job** means one output built from a variable font, run in a worker process.

## The four ways to hurt yourself

1. **Renaming notices.** Replacing the family name everywhere also rewrites the copyright and trademark ("The Inter **Clear** Project Authors"). Rename only the name IDs in `naming.FAMILY_NAME_IDS` and ≥ 256.
2. **Native imports at module level.** `ttfautohint`, `skia-pathops` (`removeOverlaps`) and `cffsubr` are imported inside functions in `convert.py` only. A top-level import makes the whole core unusable where they don't exist - including the website, which never installs them.
3. **Side effects in the core.** `core.py` and everything below it never print, exit, read or write files. Raise `FontmintError`; `cli.py` turns it into a message.
4. **Writing as you go.** The CLI prepares every input, checks that no two inputs write the same file, builds every job, and only then writes. Keep it that way, or one bad font or failing job leaves a half-finished build behind.

## Where code lives

- `fontmint/core.py` - the pipeline: `Options` → `prepare()` → `Prepared` (files + jobs) → `build_job()`. Also `mint()` and `inspect()`.
- `fontmint/axes.py` - axis values (`400,700`, `300:700`, `all`) and their combinations.
- `fontmint/features.py` - listing, freezing and disabling features.
- `fontmint/metrics.py` - line height and letter spacing.
- `fontmint/subset.py` - keeping only some characters (`--subset`).
- `fontmint/naming.py` - family renaming, style names, name records, weight/width classes.
- `fontmint/convert.py` - TrueType → OTF and autohinting. The only module that uses native helpers.
- `fontmint/common.py` - `FontmintError`, `FORMATS`, loading/saving fonts.
- `fontmint/cli.py` - argparse, file I/O, parallel builds. Its module docstring is the `--help` epilog.
- `tests/` - `unittest` suite; `tests/fixtures.py` builds tiny fonts in code.
- `assets/` - the logo.
- `web/` - the website: a static React page on GitHub Pages that runs the core in Pyodide, in Web Workers.
  - `web/fontmint_web.py` - the glue the page calls: plain dicts in and out, the web's rules (never hinted, no static OTF), progress events. Tested by `tests/test_web.py` on desktop Python.
  - `web/src/pyodide/fontmint.ts` - starts Pyodide, installs the wheels, wraps the glue in a typed API. Shared by the worker (`src/worker.ts`), the smoke test and `scripts/bench.ts`.
  - `web/src/store.ts` - the page's one zustand store: fonts, options, and the build across workers.
  - `web/src/lib/options.ts` - the form: its checks as you type, the options sent to the glue, and the matching CLI command.
  - `web/src/components/` - the page; `components/ui/` holds shadcn components (Base UI), copied in and edited.
  - `web/scripts/assets.ts` - downloads Pyodide and fontTools (checked against pinned hashes), builds the fontmint wheel, writes `public/manifest.json`.

Dependency direction: `common` ← `features` / `naming` / `axes` / `metrics` / `subset` / `convert` ← `core` ← `cli`. Nothing imports `cli`.

How a font flows through these modules: [docs/architecture.md](docs/architecture.md). Exactly what gets built, and how files and styles are named: [docs/output-rules.md](docs/output-rules.md).

## Setup and running

- `python3 -m venv .venv && .venv/bin/pip install -e .` sets up a development install.
- `.venv/bin/fontmint FONT --info` shows axes, named instances, features and languages.
- `.venv/bin/fontmint FONT --features ss01 --name "X" --output /tmp/x` runs the tool. Write test output outside the repo; `dist/` is gitignored but easy to forget.
- The website needs [Bun](https://bun.com) and the development install above. In `web/`: `bun install`, then `bun run assets` (again after changing `fontmint/`, to rebuild the wheel the page loads), then `bun run dev` for a dev server with hot reload. `bun run build` writes `web/dist/`; `bun run serve` serves it under `/fontmint/`, as GitHub Pages does.

## Verifying

- Run `.venv/bin/python -m unittest` after every change. It takes about two seconds.
- Behavior changes ship with focused tests in the matching `tests/test_<module>.py`. Extend an existing case where one fits before adding a new one.
- Bug fixes get a failing test first, then the fix.
- Build test fonts with `tests/fixtures.py`. Never commit binary font files.
- When refactoring, prove outputs didn't change by comparing font tables before and after: [docs/testing.md](docs/testing.md).
- For changes that touch real-world font structure (composites, overlaps, many lookups), also run a real family such as Inter once. The synthetic fixtures can't cover everything.
- For changes in `web/` (or to `fontmint/`, which the page runs), in `web/`: `bunx oxfmt`, `bun run lint`, `bun run typecheck`, `bun test` (unit and component tests), `bun run smoke` (fontmint in Pyodide), and `bun run build && bun run e2e` (Playwright in Chromium and Firefox). CI runs all of these on pull requests and before each deploy.

## Changing behavior

- **New option:** add it to `Options` in `core.py`, map it in `cli.py`, and document it in the README (_Options_ table and an example) and in the `cli.py` module docstring. If the page should offer it: `web_options()` in `web/fontmint_web.py`, then `webOptions()` and `cliCommands()` in `web/src/lib/options.ts` and a field in `Options.tsx`.
- **Changed checks:** the page checks fields as the user types, with fontmint's rules repeated in `formErrors()` (`web/src/lib/options.ts`): `naming.check_name`'s characters, `LINE_HEIGHT_RANGE`, `LETTER_SPACING_RANGE`, character ranges, axis values and style names. Change both together; the core still checks everything when building.
- **Different outputs:** update [docs/output-rules.md](docs/output-rules.md) and the README in the same change.
- **CLI:** long options only, `allow_abbrev=False`. Axis flags require a value (`--weight all`); an optional value would swallow a following font filename.
- **Jobs** run in worker processes, so `Job` must stay plain picklable data.

## Documentation

- `README.md` is for users and contributors: what fontmint does, how to install and use it, options, outputs.
- `docs/` holds decisions, constraints and traps that are hard to see from the code. Before adding a paragraph, ask what a maintainer would get wrong without it. If reading the code answers the question, leave it out.
- When a documented rule changes, rewrite or remove the old text instead of appending a new account.
- `CHANGELOG.md` lists what changed for users of the command line and library, per version; `web/CHANGELOG.md` does the same for the website. Add a line under the next version for every change a user can notice - in both when a core change shows on the website too.
- Format Markdown with `npx --yes oxfmt README.md AGENTS.md CHANGELOG.md docs` (`--check` to verify without writing).

## Releasing

The command line and the website have their own versions, tags and GitHub Releases. Both release only when the maintainer asks.

- **Command line and library:** bump `version` in `pyproject.toml`, give the changes a `## <version>` section in `CHANGELOG.md`, then tag `v<version>`. `.github/workflows/release-cli.yml` runs every check and creates the release with the wheel, the source archive and that section as notes.
- **Website:** bump `version` in `web/package.json`, add its section to `web/CHANGELOG.md`, then tag `web-v<version>`. `.github/workflows/release-web.yml` runs every check, deploys to GitHub Pages and creates the release.
- A tag that doesn't match its version file, or a version without a changelog section, fails the release before anything is published.
- A website release runs the core as it is at that commit, which can be ahead of the last command-line release; the footer shows the website's version, linked to its release, and the commit on hover.

## Commits

- Never commit or push unless the developer explicitly asks.
- Plain-language commit titles that say what changed for the user: `fix: renaming no longer touches copyright notices`.
- Do not commit build output, test fonts or scratch files.

## Taste

- Python 3.11+ (fontTools 4.66 and newer need it), type hints, `from __future__ import annotations`, docstrings on public functions, lines up to about 120 characters. There is no linter config; match the surrounding code.
- Standard library first. Python tests use `unittest`; don't add test or tooling dependencies to the Python package.
- The website: TypeScript, React with React Compiler (don't import `useMemo`, `useCallback` or `memo`; oxlint rejects them), Tailwind, exact versions in `web/package.json`. Build the page from the shadcn components in `web/src/components/ui/` (add missing ones with `bunx shadcn add`; it imports `cn` from a package named `cn` and adds that package to `package.json`, so point the import at `@/lib/utils` and remove the package); hand-write an element only where shadcn has nothing that fits, such as the drop area or the preview's text box.
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
- Names read from a font (family, PostScript name, axis tags) are untrusted: anything that becomes a path goes through `naming.safe_path_part`. `--name` is validated by `naming.check_name` instead.
- Name records can hold bytes that don't decode (old Mac records). Read them with `common.text`, never `toUnicode()`, and don't write back a record that came out with U+FFFD.
- A CFF charstring only states its width when it differs from the font's default width, and fontTools' `T2WidthExtractor.gotWidth` is set either way. `metrics._sync_cff_widths` tells the two apart; overwriting the first number of a charstring that states no width destroys its outline.
- Whether a glyph has a width can depend on the axis values, so letter spacing is added after instancing (`Job.letter_spacing`), not to the variable font the jobs start from.
- `bun run dev` doesn't find a file created while it runs when the import goes through the `@/` alias ("Could not resolve"): restart it after adding one, e.g. a new shadcn component.
- The website deploys only on a `web-v*` tag or by hand (`.github/workflows/release-web.yml`), never on a push to `main`: the public page would run unreleased code on people's fonts.
- `common.load(check=True)` decompiles every table on a throwaway copy to catch damaged files, then returns a fresh lazy font - decompiled tables get re-serialized on save, which would change pass-through fonts.
