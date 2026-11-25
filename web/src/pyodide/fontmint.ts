// Starts Pyodide with fontmint from the site's own files, and wraps the glue
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

export type Fontmint = {
  manifest: Manifest;
  describe(name: string, font: Uint8Array): FontInfo;
  /** Throws if the font is damaged anywhere, also where describe() doesn't look. */
  check(name: string, font: Uint8Array): void;
  /** Plans one font that passed check(); any worker can run its jobs. */
  prepare(name: string, font: Uint8Array, options: WebOptions, report: (event: BuildEvent) => void): Plan;
  /** Throws if two inputs (each one's prepare() paths) would write the same file. */
  checkClashes(outputs: string[][]): void;
  runJob(name: string, job: Uint8Array, source: Uint8Array, report: (event: BuildEvent) => void): Files;
  zipFiles(files: Files, entries: ReportEntry[], report: (event: BuildEvent) => void): Uint8Array;
};

/** `base` is the URL (browser) or folder (tests) holding pyodide/. */
export async function loadFontmint(base: string, manifest: Manifest): Promise<Fontmint> {
  const indexURL = `${base}pyodide/${manifest.pyodide}/`;
  const { loadPyodide }: typeof import("pyodide") = await import(`${indexURL}pyodide.mjs`);
  const pyodide = await loadPyodide({
    indexURL,
    // Has fontTools and fontmint too.
    stdLibURL: base + manifest.python,
    packages: ["brotli"],
  });
  // The glue module isn't part of the zip; it's bundled into the worker as text.
  pyodide.FS.writeFile("/home/pyodide/fontmint_web.py", glueSource);
  return wrap(pyodide, pyodide.pyimport("fontmint_web"), manifest);
}

type Convertible = PyProxy & { toJs(options: { dict_converter: typeof Object.fromEntries }): unknown };

// Python passes each event as a dict; Pyodide frees it once the callback returns.
const reporter = (report: (event: BuildEvent) => void) => (event: Convertible) =>
  report(event.toJs({ dict_converter: Object.fromEntries }) as BuildEvent);

function wrap(pyodide: PyodideAPI, web: PyProxy & Record<string, Function>, manifest: Manifest): Fontmint {
  const call = <T>(fn: Function, ...args: unknown[]): T => {
    // Bytes too: otherwise Python reads them one number at a time (0.6 s for 4 MB).
    const pyArgs = args.map((arg) => (typeof arg === "object" ? pyodide.toPy(arg) : arg));
    try {
      const result = fn(...pyArgs);
      if (!(result instanceof pyodide.ffi.PyProxy)) return result as T;
      const converted = (result as Convertible).toJs({ dict_converter: Object.fromEntries });
      result.destroy();
      return converted as T;
    } catch (error) {
      throw userError(error);
    } finally {
      for (const arg of pyArgs) if (arg instanceof pyodide.ffi.PyProxy) arg.destroy();
    }
  };

  return {
    manifest,
    describe: (name, font) => call(web.describe!, name, font),
    check: (name, font) => call(web.check!, name, font),
    prepare: (name, font, options, report) => {
      // toPy() turns null into JsNull, not None: leave unset options out instead.
      const set = Object.fromEntries(Object.entries(options).filter(([, v]) => v != null));
      return call(web.prepare!, name, font, set, reporter(report));
    },
    checkClashes: (outputs) => call(web.check_clashes!, outputs),
    runJob: (name, job, source, report) => call(web.run_job!, name, job, source, reporter(report)),
    zipFiles: (files, entries, report) => call(web.zip_files!, files, entries, manifest.site, reporter(report)),
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
