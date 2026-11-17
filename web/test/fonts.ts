// FontInfo values like describe() returns, for tests.
import type { FontInfo } from "../src/lib/types";

export function fontInfo(change: Partial<FontInfo> = {}): FontInfo {
  return {
    family: "Test Sans",
    variable: true,
    cff2: false,
    axes: [
      ["wght", 100, 400, 900],
      ["wdth", 75, 100, 100],
    ],
    instances: [
      ["Regular", { wght: 400, wdth: 100 }],
      ["Bold", { wght: 700, wdth: 100 }],
    ],
    features: ["aalt", "calt", "liga", "ss01", "ss02", "zero", "ccmp"],
    positioning: ["kern", "mark"],
    feature_names: { ss01: "Slashed zero" },
    languages: ["ROM"],
    italic: false,
    line_height: 1.21,
    changes: { ss01: [0x30, 0x49] },
    ...change,
  };
}
