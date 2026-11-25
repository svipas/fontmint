// A fontmint worker: Pyodide with fontmint, answering the page's calls (lib/protocol.ts).
// Pyodide starts on the first call; the page terminates the worker when it's done with it.
import { type Fontmint, loadFontmint } from "./pyodide/fontmint";
import { type FromWorker, type ToWorker, transferables } from "./lib/protocol";
import { type BuildEvent, FontmintError, type Manifest } from "./lib/types";

const base = new URL("./", self.location.href).href;
// `self` is typed as Bun's global here; in the browser it's the worker's scope.
const post = (message: FromWorker, transfer: Transferable[] = []) => self.postMessage(message, transfer as never);

let fontmint: Promise<Fontmint> | undefined;
let started = false;

self.addEventListener("message", async ({ data }: MessageEvent<ToWorker>) => {
  const report = (event: BuildEvent) => post({ type: "event", id: data.id, event });
  try {
    fontmint ??= start().catch((error) => {
      throw new Error(loadFailure(error));
    });
    const fm = await fontmint;
    started = true;
    let value: unknown;
    if (data.call === "start") value = fm.manifest;
    else if (data.call === "describe") value = fm.describe(data.name, data.font);
    else if (data.call === "prepare") value = fm.prepare(data.name, data.font, data.options, report);
    else if (data.call === "checkClashes") value = fm.checkClashes(data.outputs) ?? null;
    else if (data.call === "runJob") value = fm.runJob(data.name, data.job, data.source, report);
    else value = fm.zipFiles(data.files, data.entries, report);
    post({ type: "result", id: data.id, value }, transferables(value));
  } catch (error) {
    post({ type: "error", id: data.id, message: messageOf(error), user: error instanceof FontmintError });
  }
});

// Pyodide reports some failures (its .wasm file not arriving) outside the promise it
// returned, which then never settles: without this, the page would wait forever.
const crash = (reason: unknown) => post({ type: "crash", message: started ? messageOf(reason) : loadFailure(reason) });
self.addEventListener("unhandledrejection", (event) => crash(event.reason));
self.addEventListener("error", (event) => crash(event.error ?? event.message));

function loadFailure(error: unknown): string {
  return `fontmint couldn't load (${messageOf(error)}). Check your connection, then add the font again.`;
}

/** Emscripten also throws plain objects, e.g. when Python can't start. */
function messageOf(error: unknown): string {
  if (error instanceof Error) return error.message;
  const message = (error as { message?: unknown } | null)?.message;
  return typeof message === "string" && message ? message : String(error);
}

async function start(): Promise<Fontmint> {
  const response = await fetch(`${base}manifest.json`);
  if (!response.ok) throw new Error(`manifest.json: HTTP ${response.status}`);
  const manifest: Manifest = await response.json();
  trackDownloads(manifest.downloads);
  return loadFontmint(base, async (path) => {
    const file = await fetch(base + path);
    if (!file.ok) throw new Error(`${path}: HTTP ${file.status}`);
    return new Uint8Array(await file.arrayBuffer());
  });
}

/** Counts the bytes of the files Pyodide and fontmint download, as they stream in, so the
 * page can show a progress bar. Wrapping fetch() sees Pyodide's own downloads too. */
function trackDownloads(sizes: Record<string, number>): void {
  const total = Object.values(sizes).reduce((sum, size) => sum + size, 0);
  let loaded = 0;
  let lastPost = 0;
  const report = (force: boolean) => {
    const now = performance.now();
    if (force || now - lastPost > 100) {
      lastPost = now;
      post({ type: "download", loaded: Math.min(loaded, total), total });
    }
  };
  const realFetch = self.fetch.bind(self);
  self.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const response = await realFetch(input, init);
    const url = input instanceof Request ? input.url : String(input);
    if (!response.body || !url.startsWith(base) || !(url.slice(base.length) in sizes)) return response;
    const counted = response.body.pipeThrough(
      new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, controller) {
          loaded += chunk.byteLength;
          report(loaded >= total);
          controller.enqueue(chunk);
        },
      }),
    );
    // Keeps the headers (WebAssembly needs Content-Type: application/wasm to stream).
    return new Response(counted, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  }) as typeof fetch;
}
