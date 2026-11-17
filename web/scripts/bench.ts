// Builds fonts in Pyodide under Bun, through the same module the page's workers use,
// and reports the time each step takes. Writes the zip next to the first font.
// bun scripts/bench.ts '{"features": "ss02", "name": "Inter Clear"}' InterVariable.ttf …
import { basename, dirname, join } from "node:path";
import { type BuildEvent, loadFontmint } from "../src/pyodide/fontmint";

const pub = join(import.meta.dir, "..", "public") + "/";
const [optionsJson = "{}", ...paths] = Bun.argv.slice(2);
const seconds = (since: number) => `${((performance.now() - since) / 1000).toFixed(1)}s`;
const print = (event: BuildEvent) =>
  console.log(
    event.type === "log"
      ? `  ${event.font}: ${event.text}`
      : event.type === "job"
        ? `  ${event.font}: ${event.done}/${event.total} ${event.style} · ${event.seconds}s`
        : `  ${event.path}`,
  );

let started = performance.now();
const fontmint = await loadFontmint(pub, (path) => Bun.file(pub + path).bytes());
console.log(
  `Pyodide ${fontmint.manifest.pyodide} + fontmint ${fontmint.manifest.fontmint} ready in ${seconds(started)}`,
);

started = performance.now();
const files: Record<string, Uint8Array> = {};
for (const path of paths) {
  const font = await Bun.file(path).bytes();
  const info = fontmint.describe(basename(path), font);
  console.log(
    `${basename(path)}: ${info.family}, ${info.variable ? "variable" : "static"}, ${info.features.length} features`,
  );
  fontmint.prepare(basename(path), font, JSON.parse(optionsJson), print);
  Object.assign(files, fontmint.build(basename(path), print));
}
const zip = fontmint.zipFiles(files, print);
const out = join(dirname(paths[0] ?? "."), "fontmint-bench.zip");
await Bun.write(out, zip);
console.log(
  `${Object.keys(files).length} files, ${(zip.length / 2 ** 20).toFixed(1)} MB zip in ${seconds(started)}: ${out}`,
);
