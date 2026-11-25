import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { type Call, transferables } from "./lib/protocol";
import { fontInfo } from "../test/fonts";
import { resetStore, setState } from "../test/store";
import { emptyForm } from "./lib/options";
import { defaultAxes, type FontEntry, nameFor, orderByName, orderFonts, pickOutput, store } from "./store";

const bytes = () => new Uint8Array(1);

test("compares the variable font when there is one", () => {
  const plan = {
    paths: ["A/variable/A[wght].ttf", "A/variable/A[wght].woff2", "A/static/A-Bold"],
  };
  const files = {
    "A/variable/A[wght].ttf": bytes(),
    "A/variable/A[wght].woff2": bytes(),
    "A/ttf-unhinted/A-Bold.ttf": bytes(),
  };
  expect(pickOutput(plan, files, new Map())).toEqual({ path: "A/variable/A[wght].ttf", location: {} });
});

test("otherwise the first static font, at its axis values", () => {
  const plan = { paths: ["A/static/A-Bold", "A/static/A-Black"] };
  const files = { "A/woff2-unhinted/A-Bold.woff2": bytes(), "A/ttf-unhinted/A-Bold.ttf": bytes() };
  expect(pickOutput(plan, files, new Map([["A-Bold", { wght: 700 }]]))).toEqual({
    path: "A/ttf-unhinted/A-Bold.ttf",
    location: { wght: 700 },
  });
});

test("never another input's font with the same name", () => {
  const files = { "A/A-Regular.ttf": bytes(), "A/ttf-unhinted/A-Regular.ttf": bytes() };
  expect(pickOutput({ paths: ["A/static/A-Regular"] }, files, new Map())?.path).toBe("A/ttf-unhinted/A-Regular.ttf");
  expect(pickOutput({ paths: ["A/A-Regular.ttf"] }, files, new Map())?.path).toBe("A/A-Regular.ttf");
});

test("nothing to compare", () => {
  expect(pickOutput({ paths: [] }, {}, new Map())).toBeNull();
});

test("each buffer is transferred once", () => {
  const shared = new Uint8Array(8);
  const files = { a: shared.subarray(0, 4), b: shared.subarray(4), c: bytes() };
  expect(transferables(files)).toHaveLength(2);
  expect(transferables(shared)).toEqual([shared.buffer]);
  expect(transferables({ files, jobs: [{ job: bytes(), source: 0 }] })).toHaveLength(3);
  expect(transferables(null)).toEqual([]);
});

const font = (name: string, info: FontEntry["info"]): FontEntry => ({
  name,
  bytes: bytes(),
  info,
  error: null,
  face: null,
});

test("uprights come before their italics, families stay in the order they were added", () => {
  const fonts = [
    font("Unread.ttf", null),
    font("Mono-Italic.ttf", fontInfo({ family: "Mono", italic: true })),
    font("Sans-Italic.ttf", fontInfo({ family: "Sans Variable", italic: true })),
    font("Sans.ttf", fontInfo({ family: "Sans" })),
    font("Mono.ttf", fontInfo({ family: "Mono" })),
  ];
  expect(orderFonts(fonts).map((f) => f.name)).toEqual([
    "Mono.ttf",
    "Mono-Italic.ttf",
    "Sans.ttf",
    "Sans-Italic.ttf",
    "Unread.ttf",
  ]);
});

test("before fonts are read, their file names give the order", () => {
  const fonts = [
    font("InterVariable-Italic.ttf", null),
    font("Mono_Oblique.otf", null),
    font("InterVariable.ttf", null),
    font("Mono.otf", null),
  ];
  expect(orderByName(fonts).map((f) => f.name)).toEqual([
    "InterVariable.ttf",
    "InterVariable-Italic.ttf",
    "Mono.otf",
    "Mono_Oblique.otf",
  ]);
});

test("an axis's default comes from the first font that has it", () => {
  const fonts = [
    { info: null },
    { info: fontInfo({ axes: [["wght", 100, 400, 900]] }) },
    {
      info: fontInfo({
        axes: [
          ["wght", 100, 300, 900],
          ["opsz", 14, 14, 32],
        ],
      }),
    },
  ];
  expect(defaultAxes(fonts)).toEqual({ wght: 400, opsz: 14 });
});

const add = (...names: string[]) => store.actions.addFiles(names.map((name) => new File(["text"], name)));

test("skipped files are named, the first few of them", async () => {
  setState({ fonts: [], notice: null });
  await add("OFL.txt", "static");
  expect(store.state.notice).toBe("Skipped, not font files: OFL.txt, static");
  await add("1", "2", "3", "4", "5", "6");
  expect(store.state.notice).toBe("Skipped, not font files: 1, 2, 3, 4, 5, 6");
  await add("1", "2", "3", "4", "5", "6", "7");
  expect(store.state.notice).toBe("Skipped, not font files: 1, 2, 3, 4, 5 and 2 more");
  expect(store.state.fonts).toEqual([]);
});

test("the name follows the fonts' suggestion until the user changes it", () => {
  const inter = font("Inter.ttf", fontInfo({ family: "Inter Variable" }));
  const mono = font("Mono.ttf", fontInfo({ family: "JetBrains Mono" }));
  for (const [name, left] of [
    ["Inter Custom", "JetBrains Mono Custom"],
    ["Mint Sans", "Mint Sans"],
    ["", ""],
  ] as const) {
    setState({ fonts: [inter, mono], form: { ...emptyForm, name } });
    store.actions.removeFont("Inter.ttf");
    expect(store.state.form.name).toBe(left);
  }
  setState({
    fonts: [mono],
    form: { ...emptyForm, name: "JetBrains Mono Custom" },
    previewAxes: { wght: 700 },
  });
  store.actions.removeFont("Mono.ttf");
  expect(store.state.form.name).toBe("");
  expect(store.state.previewAxes).toEqual({});
});

test("the suggested name comes from the first font read", () => {
  expect(nameFor([font("A.ttf", null), font("B.ttf", fontInfo({ family: "Inter Variable" }))])).toBe("Inter Custom");
  expect(nameFor([font("A.ttf", null)])).toBe("");
});

type Message = { id: number; call: Call; name?: string };

class FakeWorker extends EventTarget {
  waiting: Message[] = [];
  constructor() {
    super();
    started.push(this);
  }
  postMessage(message: Message) {
    this.waiting.push(message);
  }
  terminate() {}
  answer(message: Message, answer: object) {
    this.waiting.splice(this.waiting.indexOf(message), 1);
    this.dispatchEvent(new MessageEvent("message", { data: { id: message.id, ...answer } }));
  }
  async answerAll() {
    const others = () => this.waiting.filter(({ call }) => call !== "check");
    for (let calls = others(); calls.length; calls = others()) {
      for (const call of calls) this.answer(call, { type: "result", value: fontInfo({ family: call.name }) });
      await Bun.sleep(0);
    }
  }
  async answerCheck(damage?: string) {
    const check = this.waiting.find(({ call }) => call === "check")!;
    this.answer(check, damage ? { type: "error", message: damage, user: true } : { type: "result", value: null });
    await Bun.sleep(0);
  }
  async crash() {
    this.dispatchEvent(new MessageEvent("message", { data: { type: "crash", message: "out of memory" } }));
    await Bun.sleep(0);
  }
  get checking() {
    return this.waiting.filter(({ call }) => call === "check").map(({ name }) => name);
  }
}

let started: FakeWorker[] = [];

async function until(ready: () => boolean | undefined) {
  while (!ready()) await Bun.sleep(1);
}

async function read(...names: string[]): Promise<FakeWorker> {
  void add(...names);
  await until(() => started.at(-1)?.waiting.some(({ call }) => call === "describe"));
  await started.at(-1)!.answerAll();
  const shown = () => store.state.fonts.filter((f) => f.info && names.includes(f.name));
  await until(() => shown().length === names.length);
  return started.at(-1)!;
}

const listed = () => store.state.fonts.map((f) => [f.name, f.error]);

describe("reading fonts and checking them for damage", () => {
  const realWorker = globalThis.Worker;

  beforeEach(() => {
    started = [];
    globalThis.Worker = FakeWorker as unknown as typeof Worker;
  });
  afterEach(() => {
    store.actions.cancelBuild();
    resetStore();
    globalThis.Worker = realWorker;
  });

  test("a font added under a removed one's name doesn't get the details of the removed one", async () => {
    const describes = () => started[0]?.waiting.filter(({ call }) => call === "describe") ?? [];
    void add("A.ttf");
    await until(() => describes().length === 1);
    store.actions.removeFont("A.ttf");
    void add("A.ttf");
    await until(() => describes().length === 2);
    started[0]!.answer(describes()[0]!, { type: "result", value: fontInfo({ family: "Removed" }) });
    await Bun.sleep(5);
    expect(store.state.fonts[0]!.info).toBeNull();
    await started[0]!.answerAll();
    await until(() => store.state.fonts[0]!.info?.family === "A.ttf");
  });

  test("one font at a time, also when more are added", async () => {
    const worker = await read("A.ttf", "B.ttf");
    await read("C.ttf");
    for (const name of ["A.ttf", "B.ttf", "C.ttf"]) {
      expect(worker.checking).toEqual([name]);
      await worker.answerCheck();
    }
    expect(worker.checking).toEqual([]);
  });

  test("a font removed meanwhile isn't checked", async () => {
    const worker = await read("A.ttf", "B.ttf", "C.ttf");
    store.actions.removeFont("B.ttf");
    await worker.answerCheck();
    expect(worker.checking).toEqual(["C.ttf"]);
  });

  test("a damaged font is listed with the error, and the name follows the rest", async () => {
    const worker = await read("A.ttf", "B.ttf");
    expect(store.state.form.name).toBe("A.ttf Custom");
    await worker.answerCheck("A.ttf: not a readable font");
    expect(listed()).toEqual([
      ["B.ttf", null],
      ["A.ttf", "A.ttf: not a readable font"],
    ]);
    expect(store.state.form.name).toBe("B.ttf Custom");
    expect(worker.checking).toEqual(["B.ttf"]);
  });

  test("a worker that stops isn't replaced just to go on", async () => {
    const worker = await read("A.ttf", "B.ttf");
    await worker.crash();
    expect(started).toHaveLength(1);
    expect(listed()).toEqual([
      ["A.ttf", null],
      ["B.ttf", null],
    ]);
    expect((await read("C.ttf")).checking).toEqual(["A.ttf"]);
    expect(started).toHaveLength(2);
  });

  test("a build waits for the checks", async () => {
    const worker = await read("A.ttf");
    void store.actions.startBuild();
    await Bun.sleep(0);
    expect(worker.waiting.map(({ call }) => call)).toEqual(["check"]);
    await worker.answerCheck("A.ttf: not a readable font");
    expect(store.state.build).toEqual({ status: "failed", error: "A.ttf: not a readable font", user: true });
  });
});
