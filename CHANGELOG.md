# Changelog

What changed in fontmint's command line and library, per version. The website has its own versions: [web/CHANGELOG.md](web/CHANGELOG.md).

## 0.2.0

- Every build comes with a `fontmint.txt` in its folder: what it was made from, what was changed, and the command that makes it again.
- Files that aren't fonts are skipped instead of stopping the run, so `fontmint folder/*` works next to a license or a readme. A damaged font still stops it.
- The file name of a custom-range variable font no longer depends on the order its axes were given in (`--axis` options, or `axes` in the library).

## 0.1.0

Initial release.

- Freeze OpenType features (`--features`), pick an alternate (`cv47=2`) and freeze a language's forms (`--language`).
- Turn features off (`--disable`).
- Rename the family (`--name`) without touching copyright, trademark or license notices.
- Line height and letter spacing (`--line-height`, `--letter-spacing`).
- Smaller fonts with only the characters you need (`--subset`).
- Variable fonts: static fonts at any axis value, custom-range variable fonts, in TTF (hinted and unhinted), OTF and WOFF2.
- Only the variable font, without static fonts (`--no-static`).
- Static fonts pass through in their own format.
- `--info` shows a font's axes, named instances, features, languages and line height.
