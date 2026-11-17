<p align="center">
  <img src="assets/logo.svg" alt="fontmint" width="440">
</p>

<p align="center">
  <strong>Mint your own builds of the fonts you use.</strong><br>
  Freeze OpenType features · rename the family · export variable &amp; static TTF, OTF and WOFF2
</p>

<p align="center">
  <a href="https://svipas.github.io/fontmint/"><strong>Try it in your browser →</strong></a>
  &nbsp;·&nbsp;
  <a href="#installation"><strong>Install the command line</strong></a>
</p>

<p align="center">
  <a href="#features">Features</a> ·
  <a href="#web-version">Web version</a> ·
  <a href="#installation">Installation</a> ·
  <a href="#usage">Usage</a> ·
  <a href="#options">Options</a> ·
  <a href="#output">Output</a> ·
  <a href="#which-files-should-i-use">Which files?</a> ·
  <a href="#use-as-a-library">Library</a> ·
  <a href="#limitations">Limitations</a>
</p>

---

Many fonts contain alternative letter shapes, such as a slashed zero, that only show up in apps where you can turn on OpenType features. fontmint makes those alternatives the default (it **freezes** the features) and gives the font a **new family name**, so your version installs next to the original. For **variable fonts** - one file that covers a range of styles along **axes** such as weight and width - it also exports **variable and static fonts at any axis value** (weight 375, Condensed, …) as TTF (hinted and unhinted), OTF and WOFF2. All in one command.

```bash
fontmint InterVariable*.ttf --features ss02 --name "Inter Clear"
```

This command builds 94 files: the Inter font with its `ss02` set (slashed zero, `I` with serifs, `l` with a tail - characters that are easy to tell apart) as the default, renamed to **Inter Clear**, in every weight and format.

The same build also runs in your browser at **[svipas.github.io/fontmint](https://svipas.github.io/fontmint/)**, and your fonts never leave your computer.

## Features

- **Freeze features** - make stylistic sets and character variants (`ss02`, `cv05`, `zero`, …) the default glyphs (letter shapes), so they appear in every app, even apps that can't turn on OpenType features. Ligatures and rules that depend on neighboring characters are updated to work with the frozen glyphs.
- **Pick an alternate** - when a feature offers several alternative shapes for a character, choose which one becomes the default: `cv47=2` picks the second.
- **Turn features off** - for example `--disable calt` for a coding font without ligatures.
- **Line height and letter spacing** - `--line-height 1.5` and `--letter-spacing 0.02`, measured like in CSS, for apps that have no such settings.
- **Smaller web fonts** - `--subset latin` keeps only the characters you need, with their features, the font's names and its hinting.
- **Rename the family** - your build installs next to the original without conflicts. Copyright, trademark and license notices are never changed. If the font's license reserves its name, choose a `--name` that doesn't contain it.
- **Works on static fonts too** - a static (non-variable) TTF, OTF or WOFF2 file keeps everything except what you change (features, name, line height, letter spacing, subset): same format, original hinting kept.
- **Variable fonts** - keep every axis (weight, width, …) in one file (TTF + WOFF2), or pick a custom range: `--weight 300:700` makes a smaller variable font with only those weights.
- **Static fonts at any axis value** - `--weight 375`, `--width 75`, `--slant -10`, `--optical-size 32`, or any other axis with `--axis`. With several axes, you get every combination.
- **Custom style names** - name a weight-375 build `Regular`, so apps treat it as the normal regular weight.
- **Hinted and unhinted** - static TTF and WOFF2 files built from variable fonts come in both versions. Hinting adds instructions that make small text sharper on low-resolution (low-DPI) Windows screens. Fonts that include their own hinting keep it.
- **OTF when you need it** - static fonts with CFF (PostScript) outlines for apps that require them, optimized to be smaller than the TTFs.
- **Fast** - fonts are built in parallel across all CPU cores.

## Web version

**[svipas.github.io/fontmint](https://svipas.github.io/fontmint/)** runs fontmint in your browser. Your fonts never leave your computer: fontmint runs on your device with [Pyodide](https://pyodide.org) (Python in WebAssembly).

It can freeze and turn off features, rename, change line height and letter spacing, subset, and build variable and static fonts at any axis value. A few things need the command line:

| Needs the command line                           | Why                                                                                                                                          |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **Hinted static fonts** (`*-hinted/`)            | ttfautohint is a native program that can't run in the browser                                                                                |
| **Static OTF fonts**                             | they need skia-pathops and cffsubr to merge and compact outlines                                                                             |
| **Picking one of several alternates** (`cv47=2`) | the page turns features on or off; the command line can pick an alternate                                                                    |
| **Large families, fast**                         | about three times slower in the browser for a family like Inter: one worker per font (at most 4), where the command line uses every CPU core |

The page shows the same build as commands you can copy, so you can move to the command line at any time.

## Installation

> [!IMPORTANT]
> Requires Python 3.11 or newer. Check with `python3 --version`; the Python included with macOS is 3.9, so install a newer one with Homebrew or from python.org.

```bash
git clone https://github.com/svipas/fontmint.git
cd fontmint
python3 -m venv .venv
.venv/bin/pip install -e .
```

Run it as `.venv/bin/fontmint`, or add a link to it in a folder on your `PATH`:

```bash
mkdir -p ~/.local/bin && ln -s "$PWD/.venv/bin/fontmint" ~/.local/bin/fontmint
```

## Usage

> [!IMPORTANT]
> Variable font files often have brackets in their names, like `OpenSans[wdth,wght].ttf`. Put these names in quotes, as in the examples below.

### Inspect a font

```bash
fontmint 'OpenSans[wdth,wght].ttf' --info
```

```text
OpenSans[wdth,wght].ttf
  family:      Open Sans
  axes:        wght 300–800 (default 400), wdth 75–100 (default 100)
  instances:   Light, Regular, SemiBold, Bold, ExtraBold, Condensed Light, Condensed Regular, …
  features:    aalt ccmp dnom frac liga … ss01 ss02 ss03 ss04 subs sups tnum zero
  positioning: mark mkmk
  languages:   APPH CAT IPPH MAH MKD MOL NAV ROM SRB
  line height: 1.36
```

If the font names its features, the names are listed under them, so you can see what each one changes:

```text
  named:       cv01  Alternate one
               …
               ss02  Disambiguation
```

### Static fonts: freeze and rename only

A static font (TTF, OTF or WOFF2) comes back in **the same format** - only what you ask for changes: features, the name, line height, letter spacing and subset. Glyph shapes, hinting and all other font data stay as they were, and no other formats are created.

```bash
fontmint FiraCode-Regular.ttf --features zero --name "Fira Code Zero"
# → dist/FiraCodeZero/FiraCodeZero-Regular.ttf
```

### Pick alternates and turn features off

Some features offer several alternative shapes for the same character (fonts like Iosevka have many). Add a number to choose one; without a number you get the first:

```bash
fontmint Iosevka-Regular.ttf --features cv47=2 --name "Iosevka Mine"
```

> [!NOTE]
> Some fonts build accented letters from a base letter and a separate accent; those letters keep their original shape, and fontmint warns about it.

`--disable` turns features off completely, for example the ligatures in a coding font (JetBrains Mono keeps them in `calt`):

```bash
fontmint JetBrainsMono*.ttf --disable calt --name "JetBrains Mono Flat"
```

### Language-specific forms

Many fonts draw some letters differently for one language, but apps only show those forms when the text is marked as that language. `--language` makes them the default. Open Sans, for example, has Romanian `ș ț` with a comma below instead of `ş ţ` with a cedilla:

```bash
fontmint 'OpenSans[wdth,wght].ttf' --features locl --language ROM --name "Open Sans RO"
```

> [!TIP]
> `--info` shows which languages a font has forms for. The tags are OpenType language tags, such as `ROM` for Romanian or `SRB` for Serbian.

### Line height and letter spacing

Some apps have no setting for the space between lines or letters. Build it into the font instead. Both values work like in CSS: `--line-height` is a multiple of the font size, and `--letter-spacing` is a fraction of it added after each character (negative values tighten):

```bash
fontmint JetBrainsMono*.ttf --name "JetBrains Mono Airy" --line-height 1.5 --letter-spacing 0.02
```

`--info` shows a font's current line height (JetBrains Mono: 1.32). Line height can be 0.5 to 3, letter spacing -0.5 to 1.

<details>
<summary>How the spacing is applied</summary>

The extra line space is split equally above and below the text, and accents and kerning stay where they belong. In a monospaced font, double-width glyphs get twice the letter spacing, so they still fill two cells.

</details>

### Smaller web fonts

A font for a website usually needs far fewer characters than the full font has. `--subset` keeps only the ones you list and removes everything else, which often makes the files several times smaller:

```bash
fontmint InterVariable.ttf --name "Inter Web" --subset latin,latin-ext --formats woff2
```

The presets are `latin`, `latin-ext`, `cyrillic`, `cyrillic-ext`, `greek` and `vietnamese` (the character sets Google Fonts uses), and you can add ranges like `U+2190-21FF`.

> [!IMPORTANT]
> Only `latin` has digits, punctuation and the space, so add it to the others: `--subset latin,cyrillic`.

Glyphs the remaining characters need stay too, such as their alternates and ligatures, and so do their features, the font's names and its hinting. Tables that can't be subset, such as bitmaps, are dropped with a warning. For the Inter variable font:

| Subset            | Characters | WOFF2  | TTF    |
| ----------------- | ---------- | ------ | ------ |
| none              | 2,852      | 352 KB | 880 KB |
| `latin`           | 284        | 108 KB | 269 KB |
| `latin,latin-ext` | 1,004      | 214 KB | 532 KB |

Subsetting works for every format, so a smaller desktop font is possible too, as long as it has every character you type.

### Variable fonts: build everything

Without axis options, you get the variable font **plus** a static font for every **named instance** - a style the designer defined, such as _Light_, _Bold_ or _Condensed Bold_ - in every format:

```bash
fontmint InterVariable.ttf InterVariable-Italic.ttf --features ss02 --name "Inter Clear"
```

If the family has a separate italic file, pass it too - each input file produces its own output. Add `--no-static` to get only the variable font.

> [!NOTE]
> Hinting and OTF conversion apply only to the static fonts; the variable font keeps its original outlines and hinting, with only your changes applied.

### Variable fonts: pick axis values

With axis options, you get **exactly** what you ask for:

```bash
# a few weights
fontmint InterVariable*.ttf --features ss02 --name "Inter Clear" --weight 400,500,600,700

# any weight, even one between the standard weights - style "W375"
fontmint JetBrainsMono*.ttf --features zero --name "JetBrains Mono Zero" --weight 375

# same weight, labeled "Regular" (the italic file becomes "Italic")
fontmint JetBrainsMono*.ttf --features zero --name "JetBrains Mono Zero" \
  --weight 375 --style-name Regular

# weights × widths → Regular, Bold, Condensed, Condensed Bold
fontmint 'OpenSans[wdth,wght].ttf' --name "Open Sans Custom" --weight 400,700 --width 75,100

# every named weight, condensed
fontmint 'OpenSans[wdth,wght].ttf' --name "Open Sans Custom" --weight all --width 75

# Inter's display optical size
fontmint InterVariable*.ttf --features ss02 --name "Inter Display Clear" \
  --weight all --optical-size 32

# custom axes by tag
fontmint 'Recursive[CASL,CRSV,MONO,slnt,wght].ttf' --name "Recursive Custom" --axis MONO=1 --slant 0,-15
```

Each axis option accepts:

| Value             | Result                                                     |
| ----------------- | ---------------------------------------------------------- |
| `400` / `400,700` | static fonts at exactly those values                       |
| `300:700`         | a **custom-range variable font** with only that range      |
| `all`             | every value the font's named instances use on that axis    |
| mixed             | `--weight 400,300:700` → a static 400 + a variable 300–700 |

Axes you don't set stay at their default value in static fonts and keep their full range in custom-range variable fonts.

### Custom-range variable fonts

A range keeps the font variable, but makes it smaller:

```bash
# weights 300–700 only
fontmint InterVariable.ttf --name "Inter Text" --weight 300:700
# → dist/InterText/variable/InterText-wght300-700[opsz,wght].ttf

# condensed only, weights 300–600
fontmint 'OpenSans[wdth,wght].ttf' --name "Open Sans Custom" --weight 300:600 --width 75
# → dist/OpenSansCustom/variable/OpenSansCustom-wght300-600-Condensed[wght].ttf
```

### Choose formats

All formats are built by default. Use `--formats` to choose some of them (variable input only - static input always keeps its format):

```bash
# web fonts only: variable WOFF2 + static WOFF2 (hinted and unhinted)
fontmint InterVariable*.ttf --features ss02 --name "Inter Clear" --formats woff2

# only the variable WOFF2, no static fonts
fontmint InterVariable*.ttf --features ss02 --name "Inter Clear" --formats woff2 --no-static
```

> [!TIP]
> Fonts without Latin letters, such as icon fonts, can't be hinted automatically; add `--no-hint` to build them without the hinted versions.

## Options

**Features and names**

| Option                  | Description                                                                  |
| ----------------------- | ---------------------------------------------------------------------------- |
| `--info`                | Show the font's axes, named instances, features, languages and line height.  |
| `--features ss02,zero`  | Features to freeze; `cv47=2` picks a feature's second alternate.             |
| `--language ROM`        | Freeze the forms the font has for this language (with `--features locl`).    |
| `--disable calt,liga`   | Features to turn off.                                                        |
| `--line-height 1.5`     | Line spacing as a multiple of the font size, like CSS.                       |
| `--letter-spacing 0.02` | Extra space after each character, as a fraction of the font size, like CSS.  |
| `--subset latin`        | Keep only these characters: a preset or ranges like `U+2190-21FF`.           |
| `--name "Inter Clear"`  | New family name. Recommended, so your build doesn't clash with the original. |

**Axes (variable fonts)**

| Option                 | Description                                                 |
| ---------------------- | ----------------------------------------------------------- |
| `--weight 400,700`     | Weight axis (`wght`).                                       |
| `--width 75,100`       | Width axis (`wdth`), in % - 75 = Condensed, 125 = Expanded. |
| `--slant -10`          | Slant axis (`slnt`), in degrees.                            |
| `--italic 0,1`         | Italic axis (`ital`).                                       |
| `--optical-size 32`    | Optical size axis (`opsz`).                                 |
| `--axis MONO=1`        | Any other axis by its tag. Repeatable.                      |
| `--style-name Regular` | Style name when exactly one static font is built.           |

All axis options take single values, `MIN:MAX` ranges, comma-separated lists of both, or `all`.

**Output**

| Option                    | Description                                                    |
| ------------------------- | -------------------------------------------------------------- |
| `--formats ttf,otf,woff2` | Output formats for variable input. Default: all.               |
| `--no-static`             | Build only the variable font, no static fonts.                 |
| `--no-hint`               | Don't build the hinted static fonts.                           |
| `--output dist`           | Output directory. Default: `./dist`.                           |
| `--jobs 8`                | Number of fonts to build in parallel. Default: number of CPUs. |
| `--version`               | Show the version.                                              |

## Output

Files are written to `dist/<FamilyName>/`. For variable input, each kind of file gets its own folder:

```text
dist/InterClear/
├── variable/        InterClear[opsz,wght].ttf / .woff2 (+ Italic)
├── ttf-unhinted/    static, unhinted
├── ttf-hinted/      static, hinted
├── otf/             static, CFF outlines
├── woff2-unhinted/  static, unhinted
└── woff2-hinted/    static, hinted
```

Custom-range variable fonts (`--weight 300:700`) go to `variable/` too, named after the range: `InterClear-wght300-700[opsz,wght].ttf`.

| `--formats` | Variable           | Static                              |
| ----------- | ------------------ | ----------------------------------- |
| `ttf`       | `variable/*.ttf`   | `ttf-unhinted/` + `ttf-hinted/`     |
| `otf`       | -                  | `otf/`                              |
| `woff2`     | `variable/*.woff2` | `woff2-unhinted/` + `woff2-hinted/` |

Static input is written straight into `dist/<FamilyName>/`, in its own format.

<details>
<summary>How static fonts are named and marked</summary>

Static fonts built with axis options are named after their axis values: `Condensed Bold Italic`, `W375` for non-standard weights, `Wdth80` for non-standard widths, `Oblique` for slanted fonts, and labels like `Opsz32` or `MONO1` for other axes that get several values in one run.

Static fonts built from a variable font are marked as monospaced when every character has the same width (apart from marks and double-width glyphs), so apps that list only monospaced fonts show them.

</details>

> [!NOTE]
> Nothing is written until every font has been built and every destination has been checked, so a failed run doesn't leave half a build behind. If you run fontmint again with the same output folder, files with the same name are overwritten and other files are kept; fontmint warns you when this happens.

## Which files should I use?

> [!NOTE]
> This is for builds from a variable font. A static font comes back as one file in its own format, so there's nothing to pick.

| Use case                           | Files                                                                                    |
| ---------------------------------- | ---------------------------------------------------------------------------------------- |
| Install on macOS                   | `variable/*.ttf` - every weight in one file; macOS ignores hinting                       |
| Install on Windows                 | `variable/*.ttf`, or `ttf-hinted/` for the sharpest small text on low-DPI screens        |
| Install on Linux                   | `variable/*.ttf`, or `ttf-hinted/` if your desktop uses full hinting on a low-DPI screen |
| Websites                           | `variable/*.woff2`, or a few files from `woff2-unhinted/` if you only need 1–2 weights   |
| Apps or workflows that require CFF | `otf/` - e.g. some print and prepress tools and older Adobe apps                         |

> [!TIP]
> TTF works everywhere - on macOS, Windows, Linux, in browsers and design apps - so use it by default. OTF contains the same design with CFF outlines; use it only when an app or workflow requires it.

> [!WARNING]
> Don't install a variable and a static build with the same family name at the same time - apps may pick the wrong one.

## Use as a library

The font logic works entirely in memory - font bytes in, file bytes out - so you can use it in your own scripts or build pipelines:

```python
from pathlib import Path
from fontmint import FontmintError, Options, inspect, mint

data = Path("InterVariable.ttf").read_bytes()
print(inspect(data).features)  # ['aalt', 'calt', …, 'ss02', …]

options = Options(
    features=["ss02", "cv05"],
    disable=["calt"],
    name="Inter Clear",
    axes={"wght": [400, 700]},  # a tuple, (300, 700), is a range
    formats={"ttf", "woff2"},
)
try:
    files = mint(data, options)
except FontmintError as e:
    raise SystemExit(f"fontmint: {e}")

for rel, content in files.items():  # {"InterClear/ttf-hinted/InterClear-Bold.ttf": b"…", …}
    Path("dist", rel).parent.mkdir(parents=True, exist_ok=True)
    Path("dist", rel).write_bytes(content)
```

Options also take the same text as the command line, like `features="ss02,cv47=2"` or `axes={"wght": "300:700"}`.

## Limitations

- Only rules that replace one glyph with another can be frozen everywhere (`ssXX`, `cvXX`, `zero`, `tnum`, …). Rules for ligatures (several characters joined into one glyph) or that depend on the neighboring characters are added to the font's default features instead, so they work in most apps, but not in editors and terminals with ligatures turned off. fontmint tells you when that happens.
- Freezing also updates ligatures and other rules that use the frozen characters. In rare cases a rule can't be updated; fontmint warns when that happens.
- Variable fonts with CFF2 outlines (variable `.otf` files) stay variable: fontmint changes them and builds custom ranges from them, but can't build static fonts from them yet.
- Font collections (`.ttc`) aren't supported; extract the fonts from them first.

## Development

```bash
.venv/bin/python -m unittest
```

The website lives in `web/` and needs [Bun](https://bun.com):

```bash
cd web
bun install
bun run assets   # Pyodide, fontTools and a fontmint wheel built from this repo
bun run dev      # dev server with hot reload
```

Tests build tiny fonts in code, so the repo contains no binary fixtures. For the project layout, design rules and how to verify changes, see [AGENTS.md](AGENTS.md) and [docs/](docs/). They are written for AI coding agents, but are just as useful for human contributors.

## Credits

fontmint is built on [fontTools](https://github.com/fonttools/fonttools), [ttfautohint](https://freetype.org/ttfautohint/), [skia-pathops](https://github.com/fonttools/skia-pathops) and [cffsubr](https://github.com/adobe-type-tools/cffsubr).

## License

fontmint is released under the [MIT License](LICENSE).
