import { expect, test } from "bun:test";
import { fontInfo } from "../../test/fonts";
import { featureLabel, featureList } from "./features";

test("optional features first, then those on by default, shaping ones last", () => {
  const list = featureList([fontInfo()]);
  expect(list.map((f) => [f.tag, f.kind, f.shaping])).toEqual([
    ["ss01", "optional", false],
    ["ss02", "optional", false],
    ["zero", "optional", false],
    ["calt", "default", false],
    ["kern", "default", false],
    ["liga", "default", false],
    ["ccmp", "default", true],
    ["mark", "default", true],
  ]);
});

test("aalt and other picker-only features are hidden", () => {
  expect(featureList([fontInfo()]).some((f) => f.tag === "aalt")).toBe(false);
});

test("optional positioning features can't be frozen, so they're left out", () => {
  expect(featureList([fontInfo({ features: [], positioning: ["cpsp", "kern"] })]).map((f) => f.tag)).toEqual(["kern"]);
});

test("several fonts: every feature of any of them", () => {
  const tags = featureList([fontInfo({ features: ["ss01"] }), fontInfo({ features: ["ss03"] })]).map((f) => f.tag);
  expect(tags).toContain("ss01");
  expect(tags).toContain("ss03");
});

test("labels: the font's own names first", () => {
  expect(featureLabel("ss01", { ss01: "Open digits" })).toBe("Open digits");
  expect(featureLabel("ss04")).toBe("Stylistic set 4");
  expect(featureLabel("cv47")).toBe("Character variant 47");
  expect(featureLabel("tnum")).toBe("Tabular figures");
  expect(featureLabel("xyzw")).toBe("xyzw");
});
