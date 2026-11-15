<p align="center">
  <img src="assets/logo.svg" alt="fontmint" width="440">
</p>

<p align="center">
  <strong>Mint your own builds of the fonts you use.</strong><br>
  Freeze OpenType features · rename the family · export variable &amp; static TTF, OTF and WOFF2
</p>

---

Make the fonts you use your own: **freeze OpenType features** and **rename the family** - and for variable fonts, export **variable and static fonts at any axis value** (weight 375, Condensed, …) as TTF (hinted and unhinted), OTF and WOFF2, in one command.

```bash
fontmint InterVariable*.ttf --features ss02 --name "Inter Clear"
```

That single command produces 94 files: Inter with its disambiguation set (`ss02`: slashed zero, serifed `I`, tailed `l`) baked in as the default, renamed to **Inter Clear**, in every weight and format.

## Features

- **Freeze features** - make stylistic sets and character variants (`ss02`, `cv05`, `zero`, …) the default glyphs, so they work everywhere, even in apps without OpenType feature controls.
- **Rename the family** - your build installs next to the original without clashing. Copyright, trademark and license notices are never touched. If a font's license reserves its name, pick a `--name` without it.
- **Works on static fonts too** - TTF, OTF, WOFF and WOFF2 pass through untouched apart from the frozen features and the new name: same format, original hinting kept.
- **Variable fonts** - keep every axis in one file (TTF + WOFF2), or trim it: `--weight 300:700` makes a smaller variable font.
- **Static fonts at any axis value** - `--weight 375`, `--width 75`, `--slant -10`, `--optical-size 32`, any custom axis with `--axis`; several axes multiply.
- **Custom style names** - label a 375 build as `Regular` so it behaves like a normal regular weight.
- **Hinted and unhinted** - static TTF and WOFF2 built from variable fonts come in both flavors, for the sharpest text on low-DPI Windows screens. Fonts that ship their own hinting keep it.
- **OTF when you need it** - static fonts with CFF outlines for apps that require them, optimized to be smaller than the TTFs.
- **Fast** - fonts are built in parallel across all CPU cores.

## Installation

Requires Python 3.10+ - check with `python3 --version` (macOS ships 3.9; install a newer one with Homebrew or python.org).

```bash
git clone https://github.com/svipas/fontmint.git
cd fontmint
python3 -m venv .venv
.venv/bin/pip install -e .
```

Run it as `.venv/bin/fontmint`, or link it onto your `PATH`:

```bash
mkdir -p ~/.local/bin && ln -s "$PWD/.venv/bin/fontmint" ~/.local/bin/fontmint
```

## Usage

Variable font files often have brackets in their names (`OpenSans[wdth,wght].ttf`). Quote those names - zsh, the macOS default shell, treats brackets as patterns.

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
```

### Static fonts: freeze and rename only

A static font (TTF, OTF, WOFF or WOFF2) comes back in **the same format** - only the frozen features and the new name change. Outlines, hinting and every other table stay as they were; no other formats are generated.

```bash
fontmint FooFont-Regular.otf --features ss01 --name "Foo New"
# → dist/FooNew/FooNew-Regular.otf
```

### Variable fonts: build everything

Without axis options you get the variable font **plus** a static font for every **named instance** the designer defined (e.g. _Light_, _Bold_, _Condensed Bold_), in every format:

```bash
fontmint InterVariable.ttf InterVariable-Italic.ttf --features ss02 --name "Inter Clear"
```

Pass the italic file too, if the family has one - each input produces its own output. The variable font itself is only frozen and renamed: fontmint adds no hinting and converts no outlines.

### Variable fonts: pick axis values

With axis options you get **exactly** what you ask for:

```bash
# a few weights
fontmint InterVariable*.ttf --features ss02 --name "Inter Clear" --weight 400,500,600,700

# any weight on the axis - style "W375"
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
| `400` / `400,700` | static fonts pinned at those values                         |
| `300:700`         | a **trimmed variable font** limited to that range           |
| `all`             | every value the font's named instances use on that axis     |
| mixed             | `--weight 400,300:700` → one static font + one variable one |

Axes you don't mention stay at their default for static fonts and keep their full range in trimmed variable fonts.

### Trim a variable font

Ranges keep the font variable but smaller:

```bash
# weights 300–700 only
fontmint InterVariable.ttf --name "Inter Light" --weight 300:700
# → dist/InterLight/variable/InterLight-wght300-700[opsz,wght].ttf

# condensed only, weights 300–600
fontmint 'OpenSans[wdth,wght].ttf' --name "Open Sans X" --weight 300:600 --width 75
# → dist/OpenSansX/variable/OpenSansX-wght300-600-Condensed[wght].ttf
```

### Choose formats

All formats are built by default. Use `--formats` to pick a subset (variable input only - static input always keeps its format):

```bash
# web fonts only: variable WOFF2 + static WOFF2 (hinted and unhinted)
fontmint InterVariable*.ttf --features ss02 --name "Inter Clear" --formats woff2
```

Fonts without Latin letters, such as icon fonts, can't be hinted automatically; add `--no-hint` to build them without the hinted versions.

## Options

| Option                    | Description                                                 |
| ------------------------- | ----------------------------------------------------------- |
| `--list-features`         | Show axes, named instances and GSUB features, then exit.    |
| `--features ss02,zero`    | Features to freeze.                                         |
| `--name "Inter Clear"`    | New family name. Recommended, so builds don't clash.        |
| `--weight 400,700`        | Weight axis (`wght`).                                       |
| `--width 75,100`          | Width axis (`wdth`), in % - 75 = Condensed, 125 = Expanded. |
| `--slant -10`             | Slant axis (`slnt`), in degrees.                            |
| `--italic 0,1`            | Italic axis (`ital`).                                       |
| `--optical-size 32`       | Optical size axis (`opsz`).                                 |
| `--axis MONO=1`           | Any other axis by its tag. Repeatable.                      |
| `--style-name Regular`    | Style name when exactly one static font is built.           |
| `--formats ttf,otf,woff2` | Output formats for variable input. Default: all.            |
| `--no-hint`               | Skip the hinted static fonts.                               |
| `--output dist`           | Output directory. Default: `./dist`.                        |
| `--jobs 8`                | Parallel workers. Default: CPU count.                       |
| `--version`               | Show the version.                                           |

All axis options take values, `MIN:MAX` ranges, comma lists of both, or `all`.

## Output

Files are written to `dist/<FamilyName>/`. For variable input, one folder per kind:

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

Static styles are named after their axis values: `Condensed Bold Italic`, `W375` for non-standard weights, `Wdth80` for non-standard widths, `Oblique` for slanted fonts, and labels like `Opsz32` or `MONO1` for other axes that take several values in one run.

Nothing is written until every font has been built and every destination checked, so a failed run doesn't leave half a build behind. Running again into the same folder overwrites files with the same name and keeps the others (fontmint warns about this).

## Which files should I use?

| Use case                           | Files                                                                                    |
| ---------------------------------- | ---------------------------------------------------------------------------------------- |
| Install on macOS                   | `variable/*.ttf` - every weight in one file; macOS ignores hinting                       |
| Install on Windows                 | `variable/*.ttf`, or `ttf-hinted/` for the sharpest small text on low-DPI screens        |
| Install on Linux                   | `variable/*.ttf`, or `ttf-hinted/` if your desktop uses full hinting on a low-DPI screen |
| Websites                           | `variable/*.woff2`, or a few files from `woff2-unhinted/` if you only need 1–2 weights   |
| Apps or workflows that require CFF | `otf/` - e.g. some print / pre-press and older Adobe tools                               |

TTF works everywhere - on macOS, Windows, Linux, in browsers and design apps - so use it by default. OTF contains the same design with CFF outlines; reach for it only when an app or workflow specifically asks for it.

Don't install a variable and a static build with the same family name at the same time - apps may pick the wrong one.

## Use as a library

The font logic works entirely in memory - bytes in, bytes out - so you can use it from your own scripts or build pipelines:

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

Options also take lists and sets: `features=["ss02", "zero"]`, `formats={"ttf", "woff2"}`, `axes={"wght": [400, 700]}`. A tuple is a range: `axes={"wght": (300, 700)}` is the same as `"300:700"`. Errors raise `fontmint.FontmintError`.

## Limitations

- Only single and alternate substitutions can be frozen (`ssXX`, `cvXX`, `zero`, …), not ligatures or contextual features. fontmint warns when a feature changes nothing.
- Glyphs reached through other features don't get the frozen variant - e.g. tabular figures (`tnum`) still use the original zero.
- Font collections (`.ttc`) aren't supported.

## Development

```bash
.venv/bin/python -m unittest
```

Tests build tiny fonts in code, so the repo contains no binary fixtures. For the project layout, design rules and how to verify changes, see [AGENTS.md](AGENTS.md) and [docs/](docs/) - written for AI coding agents, equally useful for human contributors.

## Credits

fontmint stands on [fontTools](https://github.com/fonttools/fonttools), [opentype-feature-freezer](https://github.com/twardoch/fonttools-opentype-feature-freezer), [ttfautohint](https://freetype.org/ttfautohint/), [skia-pathops](https://github.com/fonttools/skia-pathops) and [cffsubr](https://github.com/adobe-type-tools/cffsubr).

## License

fontmint is released under the [MIT License](LICENSE).
