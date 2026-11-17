import { expect, test } from "bun:test";
import { fontInfo } from "../../test/fonts";
import { changedCharacters, featureSettings, metricsStyle, variationSettings } from "./preview";

test("frozen features on, disabled ones off", () => {
  expect(featureSettings({ freeze: ["ss02", "zero"], disable: ["calt"], language: "" })).toBe(
    `"ss02" 1, "zero" 1, "calt" 0`,
  );
  expect(featureSettings({ freeze: [], disable: [], language: "" })).toBe("normal");
  expect(featureSettings({ freeze: [], disable: [], language: "ROM" })).toBe(`"locl" 1`);
});

test("tags from the font can't inject CSS", () => {
  expect(featureSettings({ freeze: [`a"; }`, "ss01"], disable: ["toolong"], language: "" })).toBe(`"ss01" 1`);
  expect(variationSettings({ wght: 500, 'x"{}': 1, opsz: Number.NaN })).toBe(`"wght" 500`);
  expect(variationSettings({})).toBe("normal");
});

test("metrics as CSS, only when set", () => {
  expect(metricsStyle({ lineHeight: "1.5", letterSpacing: "0.02" })).toEqual({
    lineHeight: "1.5",
    letterSpacing: "0.02em",
  });
  expect(metricsStyle({ lineHeight: "", letterSpacing: "abc" })).toEqual({});
});

test("characters the frozen features change", () => {
  const info = fontInfo({ changes: { ss01: [0x30, 0x49], zero: [0x30] } });
  expect([...changedCharacters(info, { freeze: ["ss01", "zero", "ss02"] })]).toEqual([0x30, 0x49]);
  expect(changedCharacters(info, { freeze: [] }).size).toBe(0);
});
