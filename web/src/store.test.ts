import { expect, test } from "bun:test";
import { transferables } from "./lib/protocol";
import { fontInfo } from "../test/fonts";
import { emptyForm } from "./lib/options";
import { defaultAxes, type FontEntry, nameFor, orderByName, orderFonts, pickOutput, useStore } from "./store";

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

const add = (...names: string[]) => useStore.getState().addFiles(names.map((name) => new File(["text"], name)));

test("skipped files are named, the first few of them", async () => {
  useStore.setState({ fonts: [], notice: null });
  await add("OFL.txt", "static");
  expect(useStore.getState().notice).toBe("Skipped, not font files: OFL.txt, static");
  await add("1", "2", "3", "4", "5", "6");
  expect(useStore.getState().notice).toBe("Skipped, not font files: 1, 2, 3, 4, 5, 6");
  await add("1", "2", "3", "4", "5", "6", "7");
  expect(useStore.getState().notice).toBe("Skipped, not font files: 1, 2, 3, 4, 5 and 2 more");
  expect(useStore.getState().fonts).toEqual([]);
});

test("the name follows the fonts' suggestion until the user changes it", () => {
  const inter = font("Inter.ttf", fontInfo({ family: "Inter Variable" }));
  const mono = font("Mono.ttf", fontInfo({ family: "JetBrains Mono" }));
  for (const [name, left] of [
    ["Inter Custom", "JetBrains Mono Custom"],
    ["Mint Sans", "Mint Sans"],
    ["", ""],
  ] as const) {
    useStore.setState({ fonts: [inter, mono], form: { ...emptyForm, name } });
    useStore.getState().removeFont("Inter.ttf");
    expect(useStore.getState().form.name).toBe(left);
  }
  useStore.setState({
    fonts: [mono],
    form: { ...emptyForm, name: "JetBrains Mono Custom" },
    previewAxes: { wght: 700 },
  });
  useStore.getState().removeFont("Mono.ttf");
  expect(useStore.getState().form.name).toBe("");
  expect(useStore.getState().previewAxes).toEqual({});
});

test("the suggested name comes from the first font read", () => {
  expect(nameFor([font("A.ttf", null), font("B.ttf", fontInfo({ family: "Inter Variable" }))])).toBe("Inter Custom");
  expect(nameFor([font("A.ttf", null)])).toBe("");
});
