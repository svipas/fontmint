# Output rules

Exactly what fontmint builds for a given input and options. Paths are relative to `--output` (default `dist/`); `<F>` is the new family name without spaces (e.g. `InterClear`).

## By input and options

| Input    | Axis options      | Output                                                                                     |
| -------- | ----------------- | ------------------------------------------------------------------------------------------ |
| static   | -                 | `<F>/<PostScriptName>.<same extension as input>` - nothing else                            |
| static   | any               | error                                                                                      |
| variable | none              | variable font (`<F>/variable/…`) + one static font per **named instance**, in every format |
| variable | values only       | static fonts for every combination - no variable font                                      |
| variable | ranges (± values) | one trimmed variable font per combination containing a range, plus statics for pinned ones |

Two inputs that would write the same path (same font twice, or two families with one `--name`) are an error. An existing family folder in `--output` gives a warning: same-named files are overwritten, others kept.

## Formats

`--formats` applies to variable input only (default: all three).

| Format  | Variable output                         | Static output (from variable)                           |
| ------- | --------------------------------------- | ------------------------------------------------------- |
| `ttf`   | `variable/<stem>.ttf` (`.otf` for CFF2) | `ttf-unhinted/` + `ttf-hinted/`                         |
| `otf`   | -                                       | `otf/` (CFF, overlaps removed, subroutinized, unhinted) |
| `woff2` | `variable/<stem>.woff2`                 | `woff2-unhinted/` + `woff2-hinted/`                     |

Without `ttf`/`woff2`: the default mode skips the variable font with a warning; ranges are an error.

## Hinting

- `*-unhinted/` never contains hinting: if the source variable font is hinted, its hinting tables, `gasp` and glyph instructions are stripped.
- `*-hinted/` keeps the source's own hinting (the instancer applies `cvar`) when the variable font is hinted, and is made with ttfautohint otherwise. "Hinted" means the font has `fpgm`, `cvt ` or glyph instructions; a lone short `prep` + `gasp` is the scan control that build tools (e.g. gftools) add to _unhinted_ fonts such as JetBrains Mono, and doesn't count.
- `--no-hint` / `Options(hint=False)` skips `*-hinted/`. ttfautohint fails on fonts without Latin reference glyphs (icon and symbol fonts); that error suggests `--no-hint`.
- Variable output and static input are never touched: whatever hinting they have stays.

## File names

- Static: `<F>-<Style without spaces>` - `InterClear-BoldItalic.ttf`, `OpenSansX-CondensedBold.otf`.
- Variable, default mode: `<F>[-Italic][<axis tags in fvar order>]` - `InterClear[opsz,wght].ttf`.
- Variable, trimmed: `<F>[-Italic]-<limits>[<remaining axes>]` - `InterClear-wght300-700[opsz,wght].ttf`, `OpenSansX-wght300-600-Condensed[wght].ttf`.
- Static input: the font's (renamed) PostScript name, original extension.

`--name` and `--style-name` may only use ASCII letters, digits, spaces and punctuation other than `[](){}<>/%\:*?"|`, so names are valid in PostScript and as file names on every OS; runs of spaces are collapsed. Without `--name`, folder and file names come from names inside the font, which can't be trusted: unsafe characters become `_`, so output never leaves `--output`. A resulting PostScript name (ID 6, or a static file stem) longer than 63 characters is an error.

## Style names (static fonts)

Named instances use the designer's subfamily name. Fonts built from axis values get a composed name, in this order:

1. width - `UltraCondensed` … `UltraExpanded` for standard `wdth` values (50, 62.5, 75, 87.5, 112.5, 125, 150, 200); `Wdth80` otherwise; nothing at 100
2. weight - `Thin` … `Black` for 100–900; `W375` otherwise
3. extra axes, including `slnt`, that take **several** values in one run - `Opsz32`, `MONO1`, `Slnt-5` (lowercase tags are capitalized)
4. `Italic` (italic source file, or `ital` ≥ 0.5) or `Oblique` (`slnt` ≠ 0)

`Regular` is dropped whenever other words remain, for composed and designer names alike: `Condensed Regular` → `Condensed`, `Regular Italic` → `Italic`.

`--style-name X` replaces the style when exactly one static font is built; italic sources get `Italic` appended (`Regular` → `Italic`).

## Name table and style bits (static fonts)

`naming.set_static_names` links styles the usual way: ID 2 holds only the Regular / Bold / Italic part, every other word joins the family in ID 1. That makes Bold and Italic link within each width, so Ctrl+B in "Condensed" switches to "Condensed Bold".

| Style            | ID 1               | ID 2          | ID 16 / 17                  |
| ---------------- | ------------------ | ------------- | --------------------------- |
| `Bold Italic`    | `Family`           | `Bold Italic` | - (removed)                 |
| `Condensed Bold` | `Family Condensed` | `Bold`        | `Family` / `Condensed Bold` |
| `SemiBold`       | `Family SemiBold`  | `Regular`     | `Family` / `SemiBold`       |
| `W375 Italic`    | `Family W375`      | `Italic`      | `Family` / `W375 Italic`    |
| `Oblique`        | `Family`           | `Italic`      | `Family` / `Oblique`        |

Plus ID 3 (`version;PSName`), 4 (`Family Style`), 6 (PostScript name); `usWeightClass` = the real weight (375 stays 375 even when styled `Regular`); `usWidthClass` from `wdth`; `fsSelection` bold (when the style contains `Bold`), italic, regular and oblique bits; `head.macStyle`.

## Renaming (all fonts)

`naming.rename_family` replaces the old family in name IDs 1, 3, 4, 6, 16, 18, 20, 21, 25 and ≥ 256, and in the CFF `FontName`, `FullName` and `FamilyName` strings of OTF fonts (replacing inside the existing strings, not re-deriving them). PostScript-style strings get the space-less family. IDs 0, 7 and 8–14 are never touched.

Without `--name` - or with `--name` set to the original family - outputs keep the original family name and a warning says they will clash with the original. A trailing ` Variable` is dropped for the output folder and for static fonts, file names and internal names alike (`Inter Variable` → `Inter/ttf-hinted/Inter-Bold.ttf`, ID 1 `Inter`, the same names as the official static Inter); the variable output's internal names are unchanged.
