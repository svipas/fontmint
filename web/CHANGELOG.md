# Website changelog

What changed on [svipas.github.io/fontmint](https://svipas.github.io/fontmint), per website version (`web/package.json`). The website has its own versions and `web-v*` tags; fontmint's command line and library are in the [main changelog](../CHANGELOG.md).

## 0.3.0

- The zip comes with a `fontmint.txt`: what the build was made from, what was changed, and the command that makes it again.
- Dropped files that aren't fonts (a license, a readme) are skipped instead of blocking the build.
- The command for the command line works in the Windows Command Prompt too: names are in double quotes.
- Custom-range variable fonts get the same file names as from the command line when several axes are set.

## 0.2.0

- Reset buttons put the preview's size and axes, and each group of options (features, spacing, characters, output), back to their defaults in one click.
- The new family name starts filled in from your font ("Inter Custom" for Inter), so you can build right away.
- A larger preview, from a bigger size or line height, no longer pushes the options down, away from your fonts.
- Large preview text wraps inside its card instead of running past the edge.
- The preview's sliders stay smooth on slower phones: the feature samples follow the axes once you stop moving them.

## 0.1.1

- The version in the footer opens its release notes, instead of the commit the site was built from.

## 0.1.0

First version.

- fontmint runs in your browser: fonts never leave your computer.
- Live preview of each feature and axis value, with the characters a feature changes marked.
- Each feature shows what it changes, in your font, with a larger view on hover or tap; fonts with many features get a search field.
- Freeze and turn off features, rename, line height, letter spacing, character subsets.
- Variable fonts as variable and static TTF and WOFF2, at the named styles or any axis value.
- Several named static fonts in one build, e.g. weight 375 as Regular and 675 as Bold.
- Fields are checked as you type, and the same build is shown as a command for the command line.
- Light and dark themes (Catppuccin), from your system or your choice.
