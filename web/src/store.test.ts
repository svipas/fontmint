import { expect, test } from "bun:test";
import { transferables } from "./lib/protocol";
import { fontInfo } from "../test/fonts";
import { type FontEntry, orderByName, orderFonts, pickOutput } from "./store";

const bytes = () => new Uint8Array(1);

test("compares the variable font when there is one", () => {
  const plan = {
    paths: ["A/variable/A[wght].ttf", "A/variable/A[wght].woff2", "A/static/A-Bold"],
    jobs: 1,
    folder: "A",
  };
  const files = {
    "A/variable/A[wght].ttf": bytes(),
    "A/variable/A[wght].woff2": bytes(),
    "A/ttf-unhinted/A-Bold.ttf": bytes(),
  };
  expect(pickOutput(plan, files, new Map())).toEqual({ path: "A/variable/A[wght].ttf", location: {} });
});

test("otherwise the first static font, at its axis values", () => {
  const plan = { paths: ["A/static/A-Bold", "A/static/A-Black"], jobs: 2, folder: "A" };
  const files = { "A/woff2-unhinted/A-Bold.woff2": bytes(), "A/ttf-unhinted/A-Bold.ttf": bytes() };
  expect(pickOutput(plan, files, new Map([["A-Bold", { wght: 700 }]]))).toEqual({
    path: "A/ttf-unhinted/A-Bold.ttf",
    location: { wght: 700 },
  });
});

test("nothing to compare", () => {
  expect(pickOutput({ paths: [], jobs: 0, folder: "A" }, {}, new Map())).toBeNull();
});

test("each buffer is transferred once", () => {
  const shared = new Uint8Array(8);
  const files = { a: shared.subarray(0, 4), b: shared.subarray(4), c: bytes() };
  expect(transferables(files)).toHaveLength(2);
  expect(transferables(shared)).toEqual([shared.buffer]);
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
