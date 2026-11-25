// Starts Pyodide, installs fontmint from the site's own files, and wraps the glue
// module (web/fontmint_web.py) in a typed API. Shared by the page's worker and the
// smoke test, so both run fontmint exactly the same way.
import type { PyodideAPI } from "pyodide";
import type { PyProxy } from "pyodide/ffi";
import glueSource from "../../fontmint_web.py" with { type: "text" };

import {
  type BuildEvent,
  type FontInfo,
  type Files,
  FontmintError,
  type Manifest,
  type Plan,
  type ReportEntry,
  type WebOptions,
} from "../lib/types";

export * from "../lib/types";

/** Reads a file of the site: fetch() in the browser, the file system in tests. */
type ReadFile = (path: string) => Promise<Uint8Array>;

export type Fontmint = {
  manifest: Manifest;
  describe(name: string, font: Uint8Array): FontInfo;
  /** Plans one font, kept by its file name until build(name). */
  prepare(name: string, font: Uint8Array, options: WebOptions, report: (event: BuildEvent) => void): Plan;
  /** Throws if two inputs (each one's prepare() paths) would write the same file. */
  checkClashes(outputs: string[][]): void;
  build(name: string, report: (event: BuildEvent) => void): Files;
  zipFiles(files: Files, entries: ReportEntry[], report: (event: BuildEvent) => void): Uint8Array;
};

/** `base` is the URL (browser) or folder (tests) holding pyodide/, wheels/ and manifest.json. */
export async function loadFontmint(base: string, read: ReadFile): Promise<Fontmint> {
  const manifest: Manifest = JSON.parse(new TextDecoder().decode(await read("manifest.json")));
  const { loadPyodide }: typeof import("pyodide") = await import(`${base}pyodide/pyodide.mjs`);
  const pyodide = await loadPyodide({ indexURL: `${base}pyodide/`, packages: ["micropip", "brotli"] });
  // Wheels are written into Pyodide's file system and installed from there, without
  // dependency resolution: everything fontmint needs is already in place, and micropip
  // must not look anything up on PyPI.
  pyodide.FS.mkdirTree("/wheels");
  for (const wheel of manifest.wheels) pyodide.FS.writeFile(`/wheels/${wheel}`, await read(`wheels/${wheel}`));
  const micropip = pyodide.pyimport("micropip");
  await micropip.install.callKwargs(
    manifest.wheels.map((wheel) => `emfs:/wheels/${wheel}`),
    { deps: false },
  );
  micropip.destroy();
  // The glue module isn't part of the fontmint wheel; it's bundled into the worker as text.
  pyodide.FS.writeFile("/home/pyodide/fontmint_web.py", glueSource);
  return wrap(pyodide, pyodide.pyimport("fontmint_web"), manifest);
}

type Convertible = PyProxy & { toJs(options: { dict_converter: typeof Object.fromEntries }): unknown };

// Python passes each event as a dict; Pyodide frees it once the callback returns.
const reporter = (report: (event: BuildEvent) => void) => (event: Convertible) =>
  report(event.toJs({ dict_converter: Object.fromEntries }) as BuildEvent);

function wrap(pyodide: PyodideAPI, web: PyProxy & Record<string, Function>, manifest: Manifest): Fontmint {
  /** Calls into Python: converts the result, frees `owned` (arguments made with toPy) and
   * turns a FontmintError into a plain message. */
  const call = <T>(fn: () => unknown, ...owned: PyProxy[]): T => {
    try {
      const result = fn();
      if (!(result instanceof pyodide.ffi.PyProxy)) return result as T;
      const converted = (result as Convertible).toJs({ dict_converter: Object.fromEntries });
      result.destroy();
      return converted as T;
    } catch (error) {
      throw userError(error);
    } finally {
      for (const proxy of owned) proxy.destroy();
    }
  };

  return {
    manifest,
    describe: (name, font) => call(() => web.describe!(name, font)),
    prepare: (name, font, options, report) => {
      // toPy() turns null into JsNull, not None: leave unset options out instead.
      const pyOptions = pyodide.toPy(Object.fromEntries(Object.entries(options).filter(([, v]) => v != null)));
      return call(() => web.prepare!(name, font, pyOptions, reporter(report)), pyOptions);
    },
    checkClashes: (outputs) => {
      const pyOutputs = pyodide.toPy(outputs);
      call(() => web.check_clashes!(pyOutputs), pyOutputs);
    },
    build: (name, report) => call(() => web.build!(name, reporter(report))),
    zipFiles: (files, entries, report) => {
      const pyFiles = pyodide.toPy(files);
      const pyEntries = pyodide.toPy(entries);
      return call(() => web.zip_files!(pyFiles, pyEntries, manifest.site, reporter(report)), pyFiles, pyEntries);
    },
  };
}

/** A FontmintError from Python becomes its message alone; anything else stays as it is.
 * Pyodide's message is the whole traceback, which ends with the raised error - after any
 * chained ones (`raise … from e`) that mention FontmintError too. */
function userError(error: unknown): unknown {
  if (error instanceof Error && (error as Error & { type?: string }).type === "FontmintError") {
    const marker = "FontmintError: ";
    const text = error.message.trimEnd();
    const at = text.lastIndexOf(marker);
    return new FontmintError(at === -1 ? text : text.slice(at + marker.length));
  }
  return error;
}
