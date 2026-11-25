# Testing

Two suites: the Python one covers the core, the command line and the website's Python glue; the website's own covers the page.

## Python

```bash
uv run python -m unittest
uv run python -m unittest -v tests.test_core
uv run python -m unittest tests.test_core.AxisOptionsTest.test_style_name
```

Only the standard library's `unittest` is used - don't add pytest or other test dependencies.

| File                     | Covers                                                                         |
| ------------------------ | ------------------------------------------------------------------------------ |
| `tests/fixtures.py`      | builds the test fonts (not a test module)                                      |
| `tests/test_axes.py`     | spec parsing, combination planning, range/axis errors                          |
| `tests/test_naming.py`   | style composition, renaming (notices, one-word families, CFF), name records    |
| `tests/test_features.py` | freezing, repairing the font's other rules, languages, disabling               |
| `tests/test_metrics.py`  | line height and letter spacing                                                 |
| `tests/test_subset.py`   | subset presets, ranges, what's kept                                            |
| `tests/test_core.py`     | end-to-end outputs for every mode, option errors, native helpers stay unloaded |
| `tests/test_report.py`   | what `fontmint.txt` says, and that the command line reads its commands back    |
| `tests/test_cli.py`      | the real command in a temp dir, `--info`, error messages + exit codes          |
| `tests/test_web.py`      | `web/fontmint_web.py`, the glue the page calls, on desktop Python              |

## Website

In `web/`, after `bun install` and `bun run assets`:

```bash
bun test
bun test src/store.test.ts
bun run smoke
bun run build && bun run e2e
bun run e2e --project chromium -g 'cancelled'
```

| Command         | Covers                                                                         | Runs in                        |
| --------------- | ------------------------------------------------------------------------------ | ------------------------------ |
| `bun test`      | `src/lib/`, the store and the main components; tests sit next to the code      | Bun with happy-dom, no Python  |
| `bun run smoke` | `src/pyodide/fontmint.ts` and the glue: what builds without the native helpers | Pyodide under Bun              |
| `bun run e2e`   | the production build: whole builds, workers, cancelling, crashes, page layout  | Playwright: Chromium + Firefox |

- `smoke` and `e2e` run the fontmint that `bun run assets` built, and `e2e` the page that `bun run build` built: run them again after a change, or the old code is tested.
- `e2e` uses a server already running on port 4173 (`bun run serve`), which may be another checkout's. It needs Playwright's browsers, once per Playwright version: `bunx playwright install chromium firefox`.
- `bun test` never starts a real worker (`store.test.ts` answers the page's calls itself), so `worker.ts` and building fonts in the store are only covered by `e2e`; it also runs the components without React Compiler, which the production build uses.
- `test/store.ts` puts the store into a known state. Component tests call its `resetStore` before each test, as they all share the one store.

## Fixtures

`tests/fixtures.py` builds fonts with fontTools' `FontBuilder` - no binary files in the repo. All are family **"Test Sans"** with rectangle glyphs. The website's `smoke` and `e2e` use some of them too (`web/test/fixture-fonts.ts` writes them to files); its unit tests need no fonts, only the `FontInfo` from `web/test/fonts.ts`.

| Function                                     | Font                                                                                                  |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `variable_ttf(italic, hinted, scan_control)` | `wght` 100–900 (default 400), `wdth` 75–100; instances Regular, Bold, Condensed, Condensed Bold       |
| `static_ttf(hinted)`                         | static TrueType                                                                                       |
| `static_otf()`                               | static CFF                                                                                            |
| `static_woff2()`                             | static WOFF2                                                                                          |
| `symbol_variable_ttf()`                      | variable font with only arrow glyphs - ttfautohint refuses it, for testing `--no-hint` and job errors |
| `mac_cmap_ttf()`                             | static font with an old Mac (format 0) cmap and a frozen glyph whose ID is above 255                  |
| `axis_swap_variable_ttf()`                   | variable font whose `0` becomes `O` at heavy weights (an `rvrn` feature variation)                    |

`hinted=True` adds dummy `fpgm`/`prep`/`cvt ` tables and glyph programs: static passthrough must keep them byte for byte, and the `*-unhinted/` outputs of a hinted variable font must have none. `scan_control=True` adds only the short `prep` + `gasp` that build tools put in unhinted fonts.

The Latin fixtures have `ss01` ("Slashed zero": `zero → zero.ss01`, `I → I.ss01`), an unfreezable `liga` ligature, and a copyright/trademark containing "Test Sans", so renaming bugs show up. Variation deltas are simple: bold adds +80 to the right edge at wght 900 (so +48 at 700), condensed −100.

Results are cached (`functools.cache`); open them with `fixtures.open_font(data)` so tests never share a mutable `TTFont`.

## Proving a refactor doesn't change outputs

Unit tests check behavior. For refactors, also compare real outputs before and after. Build with the old code into `before/`, with the new code into `after/`, then compare every table except `head` (timestamps/checksums always change):

```python
from pathlib import Path
from fontTools.ttLib import TTFont

before, after = Path("before"), Path("after")
files = sorted(p.relative_to(before) for p in before.rglob("*.*"))
assert files == sorted(p.relative_to(after) for p in after.rglob("*.*")), "file lists differ"
for rel in files:
    a, b = TTFont(before / rel), TTFont(after / rel)
    for tag in a.keys():
        if tag not in ("GlyphOrder", "head") and a.getTableData(tag) != b.getTableData(tag):
            print(rel, tag)
```

No output means identical fonts. To keep the old code runnable, copy the `fontmint/` package to a temporary folder and run `uv run --project /path/to/fontmint python -m fontmint` from there (the current directory wins over the editable install).

## Real fonts (optional smoke test)

The synthetic fixtures don't exercise real-world complexity (composites, hundreds of lookups, overlaps). Before a release, run a real family, e.g. Inter 4.x:

```bash
uv run fontmint InterVariable*.ttf --features ss02 --name "Inter Clear" --output /tmp/inter-check
# expect 94 files; static fonts: '0' maps to zero.slash, copyright unchanged
```
