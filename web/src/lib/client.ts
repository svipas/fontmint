// The page's side of a fontmint worker: each call is a promise; events and download
// progress arrive through callbacks.
import { type Call, type Calls, type FromWorker, type ToWorker, transferables } from "./protocol";
import { type BuildEvent, type Files, FontmintError, type ReportEntry, type WebOptions } from "./types";

type Pending = { resolve: (value: unknown) => void; reject: (error: Error) => void; onEvent?: (e: BuildEvent) => void };

export class FontmintWorker {
  private readonly worker: Worker;
  private readonly pending = new Map<number, Pending>();
  private nextId = 0;
  /** Why the worker stopped; calls fail with it from then on. */
  private stoppedBy: Error | null = null;
  /** Resolves once Pyodide and fontmint are loaded. */
  readonly ready: Promise<Calls["start"]["result"]>;

  constructor(onDownload?: (loaded: number, total: number) => void) {
    this.worker = new Worker("worker.js", { type: "module" });
    this.worker.addEventListener("message", ({ data }: MessageEvent<FromWorker>) => {
      if (data.type === "download") return onDownload?.(data.loaded, data.total);
      if (data.type === "crash") return this.stop(new Error(data.message));
      const pending = this.pending.get(data.id);
      if (!pending) return;
      if (data.type === "event") return pending.onEvent?.(data.event);
      this.pending.delete(data.id);
      if (data.type === "result") pending.resolve(data.value);
      else pending.reject(data.user ? new FontmintError(data.message) : new Error(data.message));
    });
    // A worker that dies (e.g. out of memory) fails every call still waiting.
    this.worker.addEventListener("error", (event) => {
      event.preventDefault();
      this.stop(new Error(event.message || "the build stopped unexpectedly (the browser may be out of memory)"));
    });
    this.ready = this.call("start", {});
    // A worker that can't start (offline, a missing file) is of no use: every call still
    // waiting fails with the reason. Callers that await `ready` see the failure too.
    this.ready.catch((error: Error) => this.stop(error));
  }

  describe(name: string, font: Uint8Array) {
    return this.call("describe", { name, font });
  }

  prepare(name: string, font: Uint8Array, options: WebOptions, onEvent: (e: BuildEvent) => void) {
    return this.call("prepare", { name, font, options }, onEvent);
  }

  checkClashes(outputs: string[][]) {
    return this.call("checkClashes", { outputs });
  }

  build(name: string, onEvent: (e: BuildEvent) => void) {
    return this.call("build", { name }, onEvent);
  }

  /** Zips `files`, which are moved into the worker (they're unusable here afterwards), with the report. */
  zip(files: Files, entries: ReportEntry[], onEvent: (e: BuildEvent) => void) {
    return this.call("zip", { files, entries }, onEvent);
  }

  terminate(): void {
    this.stop(new CancelledError());
  }

  /** True once the worker has ended, on purpose or not; it takes no more calls. */
  get stopped(): boolean {
    return this.stoppedBy !== null;
  }

  private stop(error: Error): void {
    if (this.stoppedBy) return;
    this.stoppedBy = error;
    this.worker.terminate();
    for (const pending of this.pending.values()) pending.reject(error);
    this.pending.clear();
  }

  private call<C extends Call>(call: C, args: Calls[C]["args"], onEvent?: (e: BuildEvent) => void) {
    const { promise, resolve, reject } = Promise.withResolvers<Calls[C]["result"]>();
    if (this.stoppedBy) {
      reject(this.stoppedBy);
      return promise;
    }
    const id = this.nextId++;
    this.pending.set(id, { resolve: resolve as (value: unknown) => void, reject, onEvent });
    const files = call === "zip" ? (args as Calls["zip"]["args"]).files : undefined;
    this.worker.postMessage({ id, call, ...args } as ToWorker, transferables(files));
    return promise;
  }
}

/** The worker was stopped on purpose (Cancel, or the page is done with it). */
export class CancelledError extends Error {
  override name = "CancelledError";
}
