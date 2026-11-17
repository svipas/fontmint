// Messages between the page (lib/client.ts) and a worker (worker.ts).
import type { BuildEvent, Files, FontInfo, Manifest, Plan, WebOptions } from "./types";

/** Each call the page can make, with what it sends and what comes back. */
export type Calls = {
  start: { args: Record<string, never>; result: Manifest };
  describe: { args: { name: string; font: Uint8Array }; result: FontInfo };
  prepare: { args: { name: string; font: Uint8Array; options: WebOptions }; result: Plan };
  checkClashes: { args: { outputs: string[][] }; result: null };
  build: { args: { name: string }; result: Files };
  zip: { args: { files: Files }; result: Uint8Array };
};

export type Call = keyof Calls;

export type ToWorker = { [C in Call]: { id: number; call: C } & Calls[C]["args"] }[Call];

export type FromWorker =
  /** Pyodide and fontmint downloading: bytes so far, of `total`. */
  | { type: "download"; loaded: number; total: number }
  | { type: "event"; id: number; event: BuildEvent }
  | { type: "result"; id: number; value: unknown }
  /** `user`: a FontmintError, whose message is meant for the user as it is. */
  | { type: "error"; id: number; message: string; user: boolean }
  /** The worker can't go on (Pyodide failed outside any call): every waiting call fails. */
  | { type: "crash"; message: string };

/** Every distinct buffer under `value` (a Uint8Array, or a Files object), to transfer instead of copy. */
export function transferables(value: unknown): ArrayBuffer[] {
  const arrays =
    value instanceof Uint8Array
      ? [value]
      : value && typeof value === "object"
        ? Object.values(value).filter((v) => v instanceof Uint8Array)
        : [];
  return [...new Set(arrays.map((a) => a.buffer as ArrayBuffer))];
}
