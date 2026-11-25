# Changelog

What changed in fontmint's command line and library, per version. The website has its own versions: [web/CHANGELOG.md](web/CHANGELOG.md).

## 0.2.1

- Needs fontTools 4.69.1, which fixes a security issue: a malicious WOFF2 file could use up all memory (GHSA-868m-5w35-h9cq).

## 0.2.0

- Every build comes with a `fontmint.txt` in its folder: what it was made from, what was changed, and the command that makes it again.
- Files that aren't fonts are skipped instead of stopping the run, so `fontmint folder/*` works next to a license or a readme. A damaged font still stops it.
- The file name of a custom-range variable font no longer depends on the order its axes were given in (`--axis` options, or `axes` in the library).
- Faster builds of variable fonts: the variable WOFF2 is compressed alongside the static fonts instead of before them.
- Library: `prepare()` leaves the variable WOFF2 to a job (`mint()` still returns everything), and `check=False` skips looking for damage in a font that `inspect()` has read.

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
