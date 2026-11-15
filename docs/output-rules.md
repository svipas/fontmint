# Output rules

Exactly what fontmint builds for a given input and options. Paths are relative to `--output` (default `dist/`); `<F>` is the new family name without spaces (e.g. `InterClear`).

## By input and options

| Input    | Axis options                           | Output                                                                                                               |
| -------- | -------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| static   | -                                      | `<F>/<PostScriptName>.<same extension as input>` - nothing else                                                      |
| static   | any                                    | error                                                                                                                |
| variable | none                                   | variable font (`<F>/variable/…`) + one static font per **named instance**, in every format                           |
| variable | single values only                     | static fonts for every combination - no variable font                                                                |
| variable | ranges (with or without single values) | one trimmed variable font per combination that contains a range, plus a static font per combination of single values |

Two inputs that would write the same path (same font twice, or two families with one `--name`) are an error. An existing family folder in `--output` gives a warning: same-named files are overwritten, others kept.

## Formats

`--formats` applies to variable input only (default: all three).

| Format  | Variable output                    | Static output (from variable)                           |
| ------- | ---------------------------------- | ------------------------------------------------------- |
| `ttf`   | `variable/<stem>.ttf`              | `ttf-unhinted/` + `ttf-hinted/`                         |
| `otf`   | - (`variable/<stem>.otf` for CFF2) | `otf/` (CFF, overlaps removed, subroutinized, unhinted) |
| `woff2` | `variable/<stem>.woff2`            | `woff2-unhinted/` + `woff2-hinted/`                     |

Without `ttf` or `woff2`, the default mode (no axis options) skips the variable font with a warning, and ranges are an error.

A variable font with CFF2 outlines is written as `.otf` (format `otf`) and WOFF2. Static fonts can't be built from it yet: the default mode builds only the variable font and warns, and single axis values are an error.

## Hinting

- `*-unhinted/` never contains hinting: if the source variable font is hinted, its hinting tables, `gasp` and glyph instructions are stripped.
- `*-hinted/` keeps the source's own hinting (the instancer applies `cvar`) when the variable font is hinted, and is made with ttfautohint otherwise. "Hinted" means the font has `fpgm`, `cvt ` or glyph instructions. A short `prep` + `gasp` on its own doesn't count: it is the scan control that build tools (e.g. gftools) add to _unhinted_ fonts such as JetBrains Mono.
- `--no-hint` / `Options(hint=False)` skips `*-hinted/`. ttfautohint fails on fonts without Latin reference glyphs (icon and symbol fonts); that error suggests `--no-hint`.
- Hinting in variable output and static input is never changed: whatever hinting they have stays.

## File names

- Static: `<F>-<Style without spaces>` - `InterClear-BoldItalic.ttf`, `OpenSansX-CondensedBold.otf`.
- Variable, default mode: `<F>[-Italic][<axis tags in fvar order>]` - `InterClear[opsz,wght].ttf`.
- Variable, trimmed: `<F>[-Italic]-<limits>[<remaining axes>]` - `InterClear-wght300-700[opsz,wght].ttf`, `OpenSansX-wght300-600-Condensed[wght].ttf`.
- Static input: the font's (renamed) PostScript name, original extension.

`--name` and `--style-name` may only use ASCII letters, digits, spaces and punctuation other than `[](){}<>/%\:*?"|`, so names are valid in PostScript and as file names on every OS. Repeated spaces become one. Without `--name`, folder and file names come from names inside the font, which can't be trusted: unsafe characters become `_`, so output never leaves `--output`. Axis tags in file names are cleaned the same way. A resulting PostScript name (ID 6, or a static file stem) longer than 63 characters is an error.

## Style names (static fonts)

Named instances use the designer's subfamily name. Fonts built from axis values get a composed name, in this order:

1. width - `UltraCondensed` … `UltraExpanded` for standard `wdth` values (50, 62.5, 75, 87.5, 112.5, 125, 150, 200); `Wdth80` otherwise; nothing at 100
2. weight - `Thin` … `Black` for 100–900; `W375` otherwise
3. extra axes, including `slnt`, that take **several** values in one run - `Opsz32`, `MONO1`, `Slnt-5` (lowercase tags are capitalized)
4. `Italic` (italic source file, or `ital` ≥ 0.5) or `Oblique` (`slnt` ≠ 0)

`Regular` is dropped whenever other words remain, for composed and designer names alike: `Condensed Regular` → `Condensed`, `Regular Italic` → `Italic`. Two-word weights and widths become one word (`Extra Bold` → `ExtraBold`), so the `Bold` in them isn't taken for the bold style.

`--style-name X` replaces the style when exactly one static font is built; italic sources get `Italic` appended (`Regular` → `Italic`).

## Name table and style bits (static fonts)

`naming.set_static_names` links styles the common way: ID 2 holds only the Regular / Bold / Italic part, every other word joins the family in ID 1. That makes Bold and Italic link within each width, so Ctrl+B in "Condensed" switches to "Condensed Bold".

| Style            | ID 1               | ID 2          | ID 16 / 17                  |
| ---------------- | ------------------ | ------------- | --------------------------- |
| `Bold Italic`    | `Family`           | `Bold Italic` | - (removed)                 |
| `Condensed Bold` | `Family Condensed` | `Bold`        | `Family` / `Condensed Bold` |
| `SemiBold`       | `Family SemiBold`  | `Regular`     | `Family` / `SemiBold`       |
| `W375 Italic`    | `Family W375`      | `Italic`      | `Family` / `W375 Italic`    |
| `Oblique`        | `Family`           | `Italic`      | `Family` / `Oblique`        |

Plus ID 3 (`version;PSName`), 4 (`Family Style`), 6 (PostScript name); `usWeightClass` = the real weight (375 stays 375 even when styled `Regular`; a font without a `wght` axis keeps its own weight and weight name); `usWidthClass` from `wdth`; `fsSelection` bold (when the style contains `Bold`), italic, regular and oblique bits; `head.macStyle`.

These names are written as Windows English records. Every other record with IDs 1–4, 6, 16–18, 21, 22 or 25 is removed, in all languages, as it would describe the variable font. Of the remaining records (copyright, license, …) the Windows ones stay; a font that has no Windows records at all keeps the ones it has.

A static font built from a variable font is marked monospaced (`post.isFixedPitch`, and PANOSE proportion for Latin text fonts) when all its characters have one width, ignoring zero-width marks and double-width glyphs. The flag is only ever set, never cleared, so a designer's own setting stays. Variable output and static input keep the flag they have. Family names (ID 1) longer than 31 characters produce a warning, for static fonts built from a variable font and for renamed static input, because some Windows apps cut them off.

## Renaming (all fonts)

`naming.rename_family` replaces the old family in name IDs 1, 3, 4, 6, 16, 18, 20, 21, 25 and ≥ 256, and in the CFF `FontName`, `FullName` and `FamilyName` strings of OTF fonts (replacing inside the existing strings, not re-deriving them). PostScript-style strings get the space-less family. IDs 0, 7 and 8–14 are never touched.

- The old family is read from the English records first (ID 16, then ID 1), so a localized name never becomes the one that gets replaced. Without ID 16, an ID 1 that also holds style words (`Acme Sans SemiBold`) is cut where the PostScript name (`AcmeSans-SemiBold`) says the family ends.
- A font that doesn't state its family in ID 1 or 16 can't be renamed; that is an error.
- A PostScript name that doesn't contain the family (`AcmeSANS-Regular` for "Acme Sans") gets the new family in front of its old suffix. Without a `-` there's no suffix to keep: the name stays and a warning says so.
- Localized versions of IDs 1, 4, 16, 18 and 21 are removed: they would keep naming the original family.
- If an identifying name still mentions the old family afterwards, a warning says so.

Without `--name`, or with `--name` set to the original family, outputs keep the original family name, and a warning says they will clash with the original (not for static input that no option changes). A trailing ` Variable` is dropped from the output folder, from all file names and from the internal names of static fonts (`Inter Variable` → `Inter/ttf-hinted/Inter-Bold.ttf`, ID 1 `Inter` - the same names as the official static Inter). The internal names of the variable output don't change.
