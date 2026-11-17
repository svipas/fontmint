// The page's state: dropped fonts, the form, the workers and the build.
import { create } from "zustand";
import { CancelledError, FontmintWorker } from "./lib/client";
import { emptyForm, type Form, webOptions } from "./lib/options";
import { loadFace } from "./lib/preview";
import { type BuildEvent, type Files, type FontInfo, FontmintError, type Manifest, type Plan } from "./lib/types";

export type FontEntry = {
  name: string;
  bytes: Uint8Array;
  info: FontInfo | null;
  error: string | null;
  /** CSS family the original is loaded under, or null (not loaded yet, or unusable). */
  face: string | null;
};

type LogLine = { text: string; warning: boolean };

/** One built file per input, loaded so the preview can show the real build. */
type BuiltFont = {
  font: string;
  /** CSS family it is loaded under. */
  face: string;
  path: string;
  /** Axis values of a static font; empty for a variable one. */
  location: Record<string, number>;
};

export type PreviewMode = "live" | "build";

export type BuildState =
  | { status: "idle" }
  | {
      status: "running";
      stage: "starting" | "preparing" | "building" | "zipping";
      done: number;
      total: number;
      /** Seconds left, estimated from the fonts built so far. */
      left: number | null;
    }
  | { status: "done"; url: string; fileName: string; size: number; files: number; seconds: number }
  | { status: "failed"; error: string; user: boolean };

type State = {
  fonts: FontEntry[];
  form: Form;
  sample: string;
  previewAxes: Record<string, number>;
  /** Pyodide download of the first worker; null before it starts. */
  download: { loaded: number; total: number } | null;
  manifest: Manifest | null;
  build: BuildState;
  log: LogLine[];
  warnings: string[];
  built: BuiltFont[];
  /** The form the last build used, to tell when the built fonts are out of date. */
  builtWith: Form | null;
  /** The preview simulates the options on the original ("live"), or shows the built font. */
  previewMode: PreviewMode;
  /** A short note for the user, e.g. a font that was added twice. */
  notice: string | null;

  addFiles(files: File[]): Promise<void>;
  removeFont(name: string): void;
  setForm(change: Partial<Form>): void;
  setSample(sample: string): void;
  setPreviewAxis(tag: string, value: number): void;
  /** Puts the preview's axes back at the fonts' default values. */
  resetPreviewAxes(): void;
  setPreviewMode(mode: PreviewMode): void;
  startBuild(): Promise<void>;
  cancelBuild(): void;
};

let primary: FontmintWorker | null = null;
let workers: FontmintWorker[] = [];

function primaryWorker(set: (state: Partial<State>) => void): FontmintWorker {
  // A worker that stopped by itself (it couldn't load, or crashed) is replaced.
  if (!primary || primary.stopped) {
    set({ download: { loaded: 0, total: 0 } });
    primary = new FontmintWorker((loaded, total) => set({ download: { loaded, total } }));
    primary.ready.then((manifest) => set({ manifest })).catch(() => {});
  }
  return primary;
}

/** Workers for a build: one per font, up to the number of cores (at most 4, ~140 MB each). */
function poolSize(fonts: number): number {
  const cores = typeof navigator !== "undefined" ? navigator.hardwareConcurrency || 2 : 2;
  return Math.max(1, Math.min(fonts, 4, cores - 1));
}

function stopWorkers(): void {
  for (const worker of new Set([primary, ...workers])) worker?.terminate();
  primary = null;
  workers = [];
}

const warnBeforeLeaving = (event: BeforeUnloadEvent) => event.preventDefault();

export const useStore = create<State>()((set, get) => ({
  fonts: [],
  form: emptyForm,
  sample: "",
  previewAxes: {},
  download: null,
  manifest: null,
  build: { status: "idle" },
  log: [],
  warnings: [],
  built: [],
  builtWith: null,
  previewMode: "live",
  notice: null,

  async addFiles(files) {
    // The build's workers end with it, and would take a font still being read with them.
    if (get().build.status === "running") return;
    const read = await Promise.all(
      files.map(async (file) => {
        try {
          return { name: file.name, bytes: new Uint8Array(await file.arrayBuffer()) };
        } catch {
          return { name: file.name, bytes: null }; // a folder, or a file that was moved away
        }
      }),
    );
    // Compared with the list as it is now, not as it was before the files were read.
    const known = new Set(get().fonts.map((f) => f.name));
    const added: FontEntry[] = [];
    const skipped: string[] = [];
    const unreadable: string[] = [];
    for (const { name, bytes } of read) {
      if (!bytes) unreadable.push(name);
      else if (known.has(name)) skipped.push(name);
      else {
        known.add(name);
        added.push({ name, bytes, info: null, error: null, face: null });
      }
    }
    const notices = [
      skipped.length ? `Already added: ${skipped.join(", ")}` : "",
      unreadable.length ? `Couldn't read: ${unreadable.join(", ")}` : "",
    ];
    // Listed, and read, in the order the file names suggest, so the upright shows first right
    // away instead of the italic a file picker hands over first; orderFonts() settles it below.
    const guessed = orderByName(added);
    set({ fonts: [...get().fonts, ...guessed], notice: notices.filter(Boolean).join(" · ") || null });
    if (!guessed.length) return;
    const worker = primaryWorker(set);
    const results = await Promise.all(
      guessed.map(async (font) => {
        const [face, described] = await Promise.all([
          loadFace(font.bytes),
          worker.describe(font.name, font.bytes).then(
            (info) => ({ info, error: null }),
            // Cancelled: the font stays unread, as it was.
            (error: Error) => ({ info: null, error: error instanceof CancelledError ? null : error.message }),
          ),
        ]);
        return [font.name, { face, ...described }] as const;
      }),
    );
    // All of them at once, in their final order: the page changes once, not once per font.
    const done = new Map(results);
    const previewAxes = { ...defaultAxes([...done.values()]), ...get().previewAxes };
    set({
      fonts: orderFonts(get().fonts.map((f) => (done.has(f.name) ? { ...f, ...done.get(f.name) } : f))),
      previewAxes,
    });
  },

  removeFont(name) {
    const fonts = get().fonts.filter((f) => f.name !== name);
    set({ fonts, notice: null });
    // Back at the start page: the last build belongs to fonts that are gone.
    if (!fonts.length) {
      const { build } = get();
      if (build.status === "done") URL.revokeObjectURL(build.url);
      set({ build: { status: "idle" }, log: [], warnings: [], built: [], builtWith: null, previewMode: "live" });
    }
  },

  setForm(change) {
    // A changed option makes the build out of date, so the preview goes back to live.
    set({ form: { ...get().form, ...change }, previewMode: "live" });
  },

  setSample(sample) {
    set({ sample });
  },

  setPreviewAxis(tag, value) {
    set({ previewAxes: { ...get().previewAxes, [tag]: value } });
  },

  resetPreviewAxes() {
    set({ previewAxes: defaultAxes(get().fonts) });
  },

  setPreviewMode(previewMode) {
    set({ previewMode });
  },

  async startBuild() {
    const fonts = get().fonts.filter((f): f is FontEntry & { info: FontInfo } => f.info !== null);
    const { form } = get();
    const previous = get().build;
    if (previous.status === "done") URL.revokeObjectURL(previous.url);
    set({
      build: { status: "running", stage: "starting", done: 0, total: 0, left: null },
      log: [],
      warnings: [],
      built: [],
      builtWith: null,
      previewMode: "live",
    });
    window.addEventListener("beforeunload", warnBeforeLeaving);
    const started = performance.now();

    const running = (change: Partial<Extract<BuildState, { status: "running" }>>) => {
      const build = get().build;
      if (build.status === "running") set({ build: { ...build, ...change } });
    };
    const locations = new Map<string, Record<string, number>>();
    let buildingSince = 0;
    const onEvent = (event: BuildEvent) => {
      if (event.type === "log") {
        set({ log: [...get().log, { text: `${event.font}: ${event.text}`, warning: event.warning }] });
        if (event.warning)
          set({ warnings: [...get().warnings, `${event.font}: ${event.text.replace(/^warning: /, "")}`] });
      } else if (event.type === "job") {
        if (event.location) locations.set(event.style, event.location);
        const build = get().build;
        if (build.status === "running") {
          const done = build.done + 1;
          const elapsed = (performance.now() - buildingSince) / 1000;
          running({ done, left: (elapsed / done) * (build.total - done) });
        }
        set({
          log: [
            ...get().log,
            {
              text: `${event.font}: ${event.style}${event.where ? ` (${event.where})` : ""} · ${event.seconds.toFixed(1)} s`,
              warning: false,
            },
          ],
        });
      } else set({ log: [...get().log, { text: `  ${event.path}`, warning: false }] });
    };

    try {
      const first = primaryWorker(set);
      await first.ready;
      // More workers start only now, so they load Pyodide from the browser cache.
      workers = [first, ...Array.from({ length: poolSize(fonts.length) - 1 }, () => new FontmintWorker())];

      running({ stage: "preparing" });
      const plans = new Map<string, Plan>();
      await Promise.all(
        workers.map(async (worker, w) => {
          for (const [i, font] of fonts.entries()) {
            if (i % workers.length !== w) continue;
            plans.set(font.name, await worker.prepare(font.name, font.bytes, webOptions(form, font.info), onEvent));
          }
        }),
      );
      await first.checkClashes(fonts.map((f) => plans.get(f.name)!.paths));

      const total = [...plans.values()].reduce((sum, plan) => sum + plan.jobs, 0);
      buildingSince = performance.now();
      running({ stage: "building", total });
      if (total) {
        const fontsWord = total === 1 ? "font" : "fonts";
        const workersWord = workers.length === 1 ? "worker" : "workers";
        set({
          log: [
            ...get().log,
            { text: `building ${total} ${fontsWord} with ${workers.length} ${workersWord}…`, warning: false },
          ],
        });
      }
      const files: Files = {};
      await Promise.all(
        workers.map(async (worker, w) => {
          for (const [i, font] of fonts.entries()) {
            if (i % workers.length === w) Object.assign(files, await worker.build(font.name, onEvent));
          }
        }),
      );

      // Before zipping, which moves the files into the worker.
      const built = (
        await Promise.all(
          fonts.map(async (font): Promise<BuiltFont | null> => {
            const output = pickOutput(plans.get(font.name)!, files, locations);
            const face = output && (await loadFace(files[output.path]!));
            return output && face ? { font: font.name, face, ...output } : null;
          }),
        )
      ).filter((entry) => entry !== null);

      running({ stage: "zipping" });
      const count = Object.keys(files).length;
      const zip = await first.zip(files, onEvent);
      const folder = plans.get(fonts[0]!.name)!.folder;
      set({
        built,
        builtWith: form,
        previewMode: built.length ? "build" : "live",
        build: {
          status: "done",
          url: URL.createObjectURL(new Blob([zip as BlobPart], { type: "application/zip" })),
          fileName: `${folder}.zip`,
          size: zip.byteLength,
          files: count,
          seconds: (performance.now() - started) / 1000,
        },
      });
    } catch (error) {
      if (error instanceof CancelledError) set({ build: { status: "idle" } });
      else
        set({
          build: {
            status: "failed",
            error: error instanceof Error ? error.message : String(error),
            user: error instanceof FontmintError,
          },
        });
    } finally {
      // WebAssembly memory never shrinks: every build ends its workers.
      stopWorkers();
      window.removeEventListener("beforeunload", warnBeforeLeaving);
    }
  },

  cancelBuild() {
    stopWorkers();
  },
}));

/** Each axis at its default value, as the first font that has the axis defines it. */
export function defaultAxes(fonts: { info: FontInfo | null }[]): Record<string, number> {
  const axes: Record<string, number> = {};
  for (const { info } of fonts) for (const [tag, , value] of info?.axes ?? []) axes[tag] ??= value;
  return axes;
}

/** The family a font belongs to, as a build names it ("Inter Variable" builds "Inter"). */
export function familyOf(info: FontInfo): string {
  return info.family.replace(/ Variable$/, "");
}

/** Fonts in the order the page lists and previews them: families as they were added, each
 * one's upright before its italic (a file picker hands over "X-Italic.ttf" before "X.ttf");
 * fonts still being read come last. */
export function orderFonts(fonts: FontEntry[]): FontEntry[] {
  const families = [...new Set(fonts.flatMap((f) => (f.info ? [familyOf(f.info)] : [])))];
  const rank = (f: FontEntry) => (f.info ? families.indexOf(familyOf(f.info)) * 2 + Number(f.info.italic) : Infinity);
  return fonts.toSorted((a, b) => (rank(a) === rank(b) ? 0 : rank(a) - rank(b)));
}

const ITALIC_NAME = /[-_ ]?(italic|oblique)/i;

/** orderFonts() guessed from the file names alone ("Inter-Italic.ttf" after "Inter.ttf"),
 * for fonts not read yet. */
export function orderByName(fonts: FontEntry[]): FontEntry[] {
  const base = (f: FontEntry) => f.name.replace(ITALIC_NAME, "").toLowerCase();
  const bases = [...new Set(fonts.map(base))];
  const rank = (f: FontEntry) => bases.indexOf(base(f)) * 2 + Number(ITALIC_NAME.test(f.name));
  return fonts.toSorted((a, b) => rank(a) - rank(b));
}

/** The built file to compare with the original: the variable font when there is one,
 * otherwise the first font built, with its axis values. */
export function pickOutput(
  plan: Plan,
  files: Files,
  locations: Map<string, Record<string, number>>,
): { path: string; location: Record<string, number> } | null {
  for (const path of plan.paths) {
    if (files[path]) return { path, location: {} };
    const stem = path.split("/").pop()!;
    for (const extension of [".ttf", ".otf", ".woff2"]) {
      const built = Object.keys(files).find((p) => p.endsWith(`/${stem}${extension}`));
      if (built) return { path: built, location: locations.get(stem) ?? {} };
    }
  }
  return null;
}
