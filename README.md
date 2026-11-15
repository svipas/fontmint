<p align="center">
  <img src="assets/logo.svg" alt="fontmint" width="440">
</p>

<p align="center">
  <strong>Mint your own builds of the fonts you use.</strong><br>
  Freeze OpenType features · rename the family · export variable &amp; static TTF, OTF and WOFF2
</p>

---

Many fonts contain alternative letter shapes, such as a slashed zero, that only show up in apps where you can turn on OpenType features. fontmint makes those alternatives the default (it **freezes** the features) and gives the font a **new family name**, so your version installs next to the original. For **variable fonts** - one file that covers a range of styles along **axes** such as weight and width - it also exports **variable and static fonts at any axis value** (weight 375, Condensed, …) as TTF (hinted and unhinted), OTF and WOFF2. All in one command.

```bash
fontmint InterVariable*.ttf --features ss02 --name "Inter Clear"
```

This command builds 94 files: the Inter font with its `ss02` set (slashed zero, `I` with serifs, `l` with a tail - characters that are easy to tell apart) as the default, renamed to **Inter Clear**, in every weight and format.

## Features

- **Freeze features** - make stylistic sets and character variants (`ss02`, `cv05`, `zero`, …) the default glyphs (letter shapes), so they appear in every app, even apps that can't turn on OpenType features. Ligatures and rules that depend on neighboring characters are updated to work with the frozen glyphs.
- **Pick an alternate** - when a feature offers several alternative shapes for a character, choose which one becomes the default: `cv47=2` picks the second.
- **Turn features off** - for example `--disable calt` for a coding font without ligatures.
- **Rename the family** - your build installs next to the original without conflicts. Copyright, trademark and license notices are never changed. If the font's license reserves its name, choose a `--name` that doesn't contain it.
- **Works on static fonts too** - a static (non-variable) TTF, OTF, WOFF or WOFF2 file keeps everything except the features you freeze or turn off and the name: same format, original hinting kept.
- **Variable fonts** - keep every axis (weight, width, …) in one file (TTF + WOFF2), or trim an axis: `--weight 300:700` makes a smaller variable font with only those weights.
- **Static fonts at any axis value** - `--weight 375`, `--width 75`, `--slant -10`, `--optical-size 32`, or any other axis with `--axis`. With several axes, you get every combination.
- **Custom style names** - name a weight-375 build `Regular`, so apps treat it as the normal regular weight.
- **Hinted and unhinted** - static TTF and WOFF2 files built from variable fonts come in both versions. Hinting adds instructions that make small text sharper on low-resolution (low-DPI) Windows screens. Fonts that include their own hinting keep it.
- **OTF when you need it** - static fonts with CFF (PostScript) outlines for apps that require them, optimized to be smaller than the TTFs.
- **Fast** - fonts are built in parallel across all CPU cores.

## Installation

Requires Python 3.10 or newer. Check with `python3 --version`; the Python included with macOS is 3.9, so install a newer one with Homebrew or from python.org.

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

Variable font files often have brackets in their names, like `OpenSans[wdth,wght].ttf`. Put these names in quotes, as in the examples below.

### Inspect a font

```bash
fontmint 'OpenSans[wdth,wght].ttf' --list-features
```

```text
OpenSans[wdth,wght].ttf
  family:    Open Sans
  axes:      wght 300–800 (default 400), wdth 75–100 (default 100)
  instances: Light, Regular, SemiBold, Bold, ExtraBold, Condensed Light, Condensed Regular, …
  features:  aalt ccmp dnom frac liga … ss01 ss02 ss03 ss04 subs sups tnum zero
  spacing:   mark mkmk (can only be disabled)
```

### Static fonts: freeze and rename only

A static font (TTF, OTF, WOFF or WOFF2) comes back in **the same format** - only the features you freeze or turn off and the new name change. Glyph shapes, hinting and all other font data stay as they were, and no other formats are created.

```bash
fontmint FooFont-Regular.otf --features ss01 --name "Foo New"
# → dist/FooNew/FooNew-Regular.otf
```

### Pick alternates and turn features off

Some features offer several alternative shapes for the same character (fonts like Iosevka have many). Add a number to choose one; without a number you get the first:

```bash
fontmint Iosevka-Regular.ttf --features cv47=2 --name "Iosevka Mine"
```

`--disable` turns features off completely, for example the ligatures in a coding font (JetBrains Mono keeps them in `calt`):

```bash
fontmint JetBrainsMono*.ttf --disable calt --name "JetBrains Mono Flat"
```

### Variable fonts: build everything

Without axis options, you get the variable font **plus** a static font for every **named instance** - a style the designer defined, such as _Light_, _Bold_ or _Condensed Bold_ - in every format:

```bash
fontmint InterVariable.ttf InterVariable-Italic.ttf --features ss02 --name "Inter Clear"
```

If the family has a separate italic file, pass it too - each input file produces its own output. The variable font itself is only frozen and renamed: fontmint doesn't add hinting or convert outlines.

### Variable fonts: pick axis values

With axis options, you get **exactly** what you ask for:

```bash
# a few weights
fontmint InterVariable*.ttf --features ss02 --name "Inter Clear" --weight 400,500,600,700

# any weight, even one between the standard weights - style "W375"
fontmint JetBrainsMono*.ttf --features zero --name "JetBrains Mono Clear" --weight 375

# same weight, labeled "Regular" (the italic file becomes "Italic")
fontmint JetBrainsMono*.ttf --features zero --name "JetBrains Mono Clear" \
  --weight 375 --style-name Regular

# weights × widths → Regular, Bold, Condensed, Condensed Bold
fontmint 'OpenSans[wdth,wght].ttf' --name "Open Sans X" --weight 400,700 --width 75,100

# every named weight, condensed
fontmint 'OpenSans[wdth,wght].ttf' --name "Open Sans X" --weight all --width 75

# Inter's display optical size
fontmint InterVariable*.ttf --features ss02 --name "Inter Display Clear" \
  --weight all --optical-size 32

# custom axes by tag
fontmint 'Recursive[CASL,CRSV,MONO,slnt,wght].ttf' --name "Rec X" --axis MONO=1 --slant 0,-15
```

Each axis option accepts:

| Value             | Result                                                      |
| ----------------- | ----------------------------------------------------------- |
| `400` / `400,700` | static fonts at exactly those values                        |
| `300:700`         | a **trimmed variable font** limited to that range           |
| `all`             | every value the font's named instances use on that axis     |
| mixed             | `--weight 400,300:700` → one static font + one variable one |

Axes you don't set stay at their default value in static fonts and keep their full range in trimmed variable fonts.

### Trim a variable font

A range keeps the font variable, but makes it smaller:

```bash
# weights 300–700 only
fontmint InterVariable.ttf --name "Inter Light" --weight 300:700
# → dist/InterLight/variable/InterLight-wght300-700[opsz,wght].ttf

# condensed only, weights 300–600
fontmint 'OpenSans[wdth,wght].ttf' --name "Open Sans X" --weight 300:600 --width 75
# → dist/OpenSansX/variable/OpenSansX-wght300-600-Condensed[wght].ttf
```

### Choose formats

All formats are built by default. Use `--formats` to choose some of them (variable input only - static input always keeps its format):

```bash
# web fonts only: variable WOFF2 + static WOFF2 (hinted and unhinted)
fontmint InterVariable*.ttf --features ss02 --name "Inter Clear" --formats woff2
```

Fonts without Latin letters, such as icon fonts, can't be hinted automatically; add `--no-hint` to build them without the hinted versions.

## Options

| Option                    | Description                                                                  |
| ------------------------- | ---------------------------------------------------------------------------- |
| `--list-features`         | Show the font's axes, named instances and features, then exit.               |
| `--features ss02,zero`    | Features to freeze; `cv47=2` picks a feature's second alternate.             |
| `--disable calt,liga`     | Features to turn off.                                                        |
| `--name "Inter Clear"`    | New family name. Recommended, so your build doesn't clash with the original. |
| `--weight 400,700`        | Weight axis (`wght`).                                                        |
| `--width 75,100`          | Width axis (`wdth`), in % - 75 = Condensed, 125 = Expanded.                  |
| `--slant -10`             | Slant axis (`slnt`), in degrees.                                             |
| `--italic 0,1`            | Italic axis (`ital`).                                                        |
| `--optical-size 32`       | Optical size axis (`opsz`).                                                  |
| `--axis MONO=1`           | Any other axis by its tag. Repeatable.                                       |
| `--style-name Regular`    | Style name when exactly one static font is built.                            |
| `--formats ttf,otf,woff2` | Output formats for variable input. Default: all.                             |
| `--no-hint`               | Don't build the hinted static fonts.                                         |
| `--output dist`           | Output directory. Default: `./dist`.                                         |
| `--jobs 8`                | Number of fonts to build in parallel. Default: number of CPUs.               |
| `--version`               | Show the version.                                                            |

All axis options take single values, `MIN:MAX` ranges, comma-separated lists of both, or `all`.

## Output

Files are written to `dist/<FamilyName>/`. For variable input, each kind of file gets its own folder:

```text
dist/InterClear/
├── variable/        InterClear[opsz,wght].ttf / .woff2 (+ Italic, trimmed fonts)
├── ttf-unhinted/    static, unhinted
├── ttf-hinted/      static, hinted
├── otf/             static, CFF outlines
├── woff2-unhinted/  static, unhinted
└── woff2-hinted/    static, hinted
```

| `--formats` | Variable           | Static                              |
| ----------- | ------------------ | ----------------------------------- |
| `ttf`       | `variable/*.ttf`   | `ttf-unhinted/` + `ttf-hinted/`     |
| `otf`       | -                  | `otf/`                              |
| `woff2`     | `variable/*.woff2` | `woff2-unhinted/` + `woff2-hinted/` |

Static input is written straight into `dist/<FamilyName>/`, in its own format.

Static fonts where every character has the same width are marked as monospaced, so apps that list only monospaced fonts show them.

Static fonts built with axis options are named after their axis values: `Condensed Bold Italic`, `W375` for non-standard weights, `Wdth80` for non-standard widths, `Oblique` for slanted fonts, and labels like `Opsz32` or `MONO1` for other axes that get several values in one run.

Nothing is written until every font has been built and every destination has been checked, so a failed run doesn't leave half a build behind. If you run fontmint again with the same output folder, files with the same name are overwritten and other files are kept; fontmint warns you when this happens.

## Which files should I use?

| Use case                           | Files                                                                                    |
| ---------------------------------- | ---------------------------------------------------------------------------------------- |
| Install on macOS                   | `variable/*.ttf` - every weight in one file; macOS ignores hinting                       |
| Install on Windows                 | `variable/*.ttf`, or `ttf-hinted/` for the sharpest small text on low-DPI screens        |
| Install on Linux                   | `variable/*.ttf`, or `ttf-hinted/` if your desktop uses full hinting on a low-DPI screen |
| Websites                           | `variable/*.woff2`, or a few files from `woff2-unhinted/` if you only need 1–2 weights   |
| Apps or workflows that require CFF | `otf/` - e.g. some print and prepress tools and older Adobe apps                         |

TTF works everywhere - on macOS, Windows, Linux, in browsers and design apps - so use it by default. OTF contains the same design with CFF outlines; use it only when an app or workflow requires it.

Don't install a variable and a static build with the same family name at the same time - apps may pick the wrong one.

## Use as a library

The font logic works entirely in memory - font bytes in, file bytes out - so you can use it in your own scripts or build pipelines:

```python
from pathlib import Path
from fontmint import Options, inspect, mint

data = Path("InterVariable.ttf").read_bytes()
print(inspect(data).features)  # ['aalt', 'calt', …, 'ss02', …]

files = mint(data, Options(features="ss02", name="Inter Clear", axes={"wght": "400,700"}))
for rel, content in files.items():  # {"InterClear/otf/InterClear-Bold.otf": b"…", …}
    Path("dist", rel).parent.mkdir(parents=True, exist_ok=True)
    Path("dist", rel).write_bytes(content)
```

Options also accept Python values instead of strings:

```python
from fontmint import FontmintError, Options, mint

options = Options(
    features={"ss02": 1, "cv05": 1},  # the number picks an alternate; 1 is the first
    disable=["calt"],
    name="Inter Clear",
    axes={"wght": [400, 700]},  # a tuple, (300, 700), is a range
    formats={"ttf", "woff2"},
)
try:
    files = mint(data, options)
except FontmintError as e:
    print(f"fontmint: {e}")
```

## Limitations

- Only features that replace one glyph with another can be frozen (`ssXX`, `cvXX`, `zero`, `tnum`, …). Ligatures (several characters joined into one glyph) and contextual features (which depend on the neighboring characters) can't be frozen, but they can be turned off with `--disable`. fontmint warns when a feature is only partly frozen or changes nothing.
- Freezing also updates ligatures and other rules that use the frozen characters. In rare cases a rule can't be updated; fontmint warns when that happens.
- Font collections (`.ttc`) aren't supported; extract the fonts from them first.

## Development

```bash
.venv/bin/python -m unittest
```

Tests build tiny fonts in code, so the repo contains no binary fixtures. For the project layout, design rules and how to verify changes, see [AGENTS.md](AGENTS.md) and [docs/](docs/). They are written for AI coding agents, but are just as useful for human contributors.

## Credits

fontmint is built on [fontTools](https://github.com/fonttools/fonttools), [ttfautohint](https://freetype.org/ttfautohint/), [skia-pathops](https://github.com/fonttools/skia-pathops) and [cffsubr](https://github.com/adobe-type-tools/cffsubr).

## License

fontmint is released under the [MIT License](LICENSE).
