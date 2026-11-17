// Smoke test: fontmint in Pyodide, from the site's own files in public/ (bun run assets),
// through the same module the page's workers use. Pyodide has none of fontmint's native
// helpers (ttfautohint, skia-pathops, cffsubr) and the wheel is installed without
// dependencies, so a build that reached one would fail here.
import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { type Files, FontmintError, loadFontmint, type WebOptions } from "../src/pyodide/fontmint";
import { writeFixtureFonts } from "../test/fixture-fonts";

const pub = join(import.meta.dir, "..", "public") + "/";
const ignore = () => {};
/** The output folders (variable, ttf-unhinted, …) of a build. */
const folders = (files: Files) => [...new Set(Object.keys(files).map((path) => path.split("/")[1]))].toSorted();

const folder = await mkdtemp(join(tmpdir(), "fontmint-smoke-"));
try {
  const fonts = writeFixtureFonts(folder);
  const fontmint = await loadFontmint(pub, (path) => Bun.file(pub + path).bytes());
  const build = async (path: string, options: WebOptions): Promise<Files> => {
    const name = path.split("/").pop()!;
    fontmint.prepare(name, await Bun.file(path).bytes(), options, ignore);
    return fontmint.build(name, ignore);
  };

  const info = fontmint.describe("TestSans.ttf", await Bun.file(fonts.variable).bytes());
  assert.equal(info.variable, true);
  assert.deepEqual(info.changes, { ss01: [0x30, 0x49] });

  // The page's defaults: variable + static TTF and WOFF2, unhinted.
  let files = await build(fonts.variable, { features: "ss01", name: "Mint Sans", formats: ["ttf", "woff2"] });
  assert.deepEqual(folders(files), ["ttf-unhinted", "variable", "woff2-unhinted"]);
  assert.equal(Object.keys(files).length, 2 + 4 * 2);

  files = await build(fonts.variable, { name: "Mint Sans", axes: { wght: "300:700" }, formats: ["woff2"] });
  assert.deepEqual(folders(files), ["variable"]);
  files = await build(fonts.variable, {
    name: "Mint Sans",
    axes: { wght: "375" },
    style_name: "Book",
    formats: ["ttf"],
  });
  assert.ok(
    Object.keys(files).some((path) => path.endsWith("/MintSans-Book.ttf")),
    Object.keys(files).join(", "),
  );

  files = await build(fonts.variable, { name: "Mint Sans", static: false, formats: ["ttf", "woff2"] });
  assert.deepEqual(folders(files), ["variable"]);

  files = await build(fonts.static, { features: "ss01", name: "Mint Sans", formats: ["ttf", "woff2"] });
  assert.equal(Object.keys(files).length, 1);

  const zip = fontmint.zipFiles(files, ignore);
  assert.deepEqual(Array.from(zip.subarray(0, 4)), [0x50, 0x4b, 0x03, 0x04], "a zip file");

  // A user error comes back as its message alone, without the traceback.
  assert.throws(
    () => fontmint.describe("Broken.ttf", new TextEncoder().encode("not a font")),
    (error: unknown) => error instanceof FontmintError && error.message.startsWith("Broken.ttf: not a readable font"),
  );
  console.log(`smoke test passed: Pyodide ${fontmint.manifest.pyodide}, fontmint ${fontmint.manifest.fontmint}`);
} finally {
  await rm(folder, { recursive: true, force: true });
}
