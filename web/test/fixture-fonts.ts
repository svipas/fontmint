// Writes the tiny test fonts from tests/fixtures.py into a folder, for the smoke and
// end-to-end tests. Runs on Bun and Node (Playwright's runner), so it uses Node's APIs.
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

const repo = join(import.meta.dirname, "..", "..");

export const FIXTURES = {
  variable: "TestSans[wght,wdth].ttf",
  italic: "TestSans-Italic[wght,wdth].ttf",
  static: "TestSans-Regular.ttf",
};

const SCRIPT = `
import sys
from pathlib import Path
from tests import fixtures as fx
folder = Path(sys.argv[1])
folder.mkdir(parents=True, exist_ok=True)
(folder / sys.argv[2]).write_bytes(fx.variable_ttf())
(folder / sys.argv[3]).write_bytes(fx.variable_ttf(italic=True))
(folder / sys.argv[4]).write_bytes(fx.static_ttf())
`;

/** Writes the fonts and returns their paths, keyed like FIXTURES. */
export function writeFixtureFonts(folder: string): typeof FIXTURES {
  const venv = join(repo, ".venv", "bin", "python");
  const python = existsSync(venv) ? venv : "python3";
  execFileSync(python, ["-c", SCRIPT, folder, FIXTURES.variable, FIXTURES.italic, FIXTURES.static], {
    cwd: repo,
    stdio: "inherit",
  });
  return {
    variable: join(folder, FIXTURES.variable),
    italic: join(folder, FIXTURES.italic),
    static: join(folder, FIXTURES.static),
  };
}
