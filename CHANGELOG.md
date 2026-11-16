# Changelog

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
