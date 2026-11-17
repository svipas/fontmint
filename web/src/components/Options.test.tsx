import { beforeEach, expect, test } from "bun:test";
import { fireEvent, render, screen } from "@testing-library/react";
import { resetStore, withFonts } from "../../test/store";
import { useStore } from "../store";
import { Options, sampleCharacters } from "./Options";

beforeEach(resetStore);

test("features come from the font, labeled with its own names", () => {
  withFonts({});
  render(<Options />);
  expect(screen.getByRole("checkbox", { name: /Slashed zero ss01/ })).toBeTruthy();
  expect(screen.getByRole("checkbox", { name: /Stylistic set 2 ss02/ })).toBeTruthy();
  expect(screen.queryByRole("checkbox", { name: /aalt/ })).toBeNull();
});

test("checking an optional feature freezes it; unchecking one on by default turns it off", () => {
  withFonts({});
  render(<Options />);
  const ss02 = screen.getByRole("checkbox", { name: /ss02/ });
  const liga = screen.getByRole("checkbox", { name: /liga/ });
  const checked = () => [ss02, liga].map((box) => box.getAttribute("aria-checked"));
  expect(checked()).toEqual(["false", "true"]);
  // Base UI's checkbox toggles through its label in happy-dom.
  fireEvent.click(screen.getByText("Stylistic set 2"));
  fireEvent.click(screen.getByText("Standard ligatures"));
  expect(useStore.getState().form.freeze).toEqual(["ss02"]);
  expect(useStore.getState().form.disable).toEqual(["liga"]);
  expect(checked()).toEqual(["true", "false"]);
});

test("output options: TTF for TrueType, OTF for CFF2, none for static fonts", () => {
  withFonts({});
  const { unmount } = render(<Options />);
  expect(screen.getByRole("checkbox", { name: "TTF" })).toBeTruthy();
  expect(screen.queryByLabelText(/Weight \(100–900\)/)).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /Axis values and style name/ }));
  expect(screen.getByLabelText(/Weight \(100–900\)/)).toBeTruthy();
  unmount();

  withFonts({ cff2: true });
  render(<Options />);
  expect(screen.getByRole("checkbox", { name: "OTF" })).toBeTruthy();
  expect(screen.queryByRole("checkbox", { name: "TTF" })).toBeNull();
});

test("static fonts get no output options", () => {
  withFonts({ variable: false, axes: [], instances: [] });
  render(<Options />);
  expect(screen.queryByText("Output")).toBeNull();
});

test("the name field asks for a name once it was left empty, and checks it as you type", () => {
  withFonts({});
  render(<Options />);
  const name = screen.getByLabelText(/New family name/);
  expect(screen.queryByText(/Give your build its own name/)).toBeNull();
  fireEvent.blur(name);
  expect(screen.getByText(/Give your build its own name/)).toBeTruthy();
  expect(name.getAttribute("aria-invalid")).toBe("true");
  fireEvent.change(name, { target: { value: "Mint/Sans" } });
  expect(screen.getByText(/found \//)).toBeTruthy();
  fireEvent.change(name, { target: { value: "Mint Sans" } });
  expect(useStore.getState().form.name).toBe("Mint Sans");
  expect(name.getAttribute("aria-invalid")).toBe("false");
});

test("advanced sections start closed, and open when something in them is set", () => {
  withFonts({});
  const { unmount } = render(<Options />);
  expect(screen.queryByLabelText(/Line height/)).toBeNull();
  unmount();
  useStore.setState({ form: { ...useStore.getState().form, lineHeight: "1.4" } });
  render(<Options />);
  expect(screen.getByLabelText(/Line height/)).toBeTruthy();
  expect(screen.getByText("line height 1.4")).toBeTruthy();
});

test("axis values are checked as you type", () => {
  withFonts({});
  render(<Options />);
  fireEvent.click(screen.getByRole("button", { name: /Axis values and style name/ }));
  fireEvent.change(screen.getByLabelText(/Weight/), { target: { value: "50" } });
  expect(screen.getByText("50 is outside this font's range, 100–900")).toBeTruthy();
});

/** The feature rows on screen, as "name + tag". */
const shown = () => [...document.querySelectorAll("li")].map((row) => row.textContent);

test("the search narrows the features by name or tag, and clears", () => {
  const tags = ["ss01", "ss02", "ss03", "ss04", "zero", "case", "calt", "liga", "ccmp"];
  withFonts({ features: tags, positioning: [] });
  render(<Options />);
  const search = screen.getByRole("textbox", { name: "Search features" });

  fireEvent.change(search, { target: { value: "SET 2" } });
  expect(shown()).toEqual(["Stylistic set 2ss02"]);
  // Rarely changed features are folded away, but a search finds them.
  fireEvent.change(search, { target: { value: "ccmp" } });
  expect(shown()).toEqual(["Glyph compositionccmp"]);
  fireEvent.change(search, { target: { value: "nothing" } });
  expect(screen.getByText(/No feature matches/)).toBeTruthy();

  fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
  expect((search as HTMLInputElement).value).toBe("");
  expect(shown()).toHaveLength(8); // all but ccmp, which is folded away again
});

test("fonts with few features have no search field", () => {
  withFonts({});
  render(<Options />);
  expect(screen.queryByRole("textbox", { name: "Search features" })).toBeNull();
});

test("a feature's sample: plain letters and digits first", () => {
  expect(sampleCharacters([0xb9, 0x31, 0x2081])).toBe("1");
  expect(sampleCharacters([0x6c, 0x13a, 0x49])).toBe("Il");
  expect(sampleCharacters([0x20, 0x29, 0x28])).toBe("(");
  expect(sampleCharacters([])).toBe("");
});

test("several custom styles, each with its own values and name", () => {
  withFonts({});
  render(<Options />);
  fireEvent.click(screen.getByRole("button", { name: /Axis values and style names/ }));
  fireEvent.change(screen.getByLabelText(/Weight/), { target: { value: "375" } });
  fireEvent.click(screen.getByRole("button", { name: "Add another style" }));
  const second = screen.getByRole("group", { name: "Style 2" });
  fireEvent.change(second.querySelector("#axis-1-wght")!, { target: { value: "675" } });
  fireEvent.change(second.querySelector("#style-1")!, { target: { value: "Bold" } });
  expect(useStore.getState().form.styles).toEqual([
    { axes: { wght: "375" }, name: "" },
    { axes: { wght: "675" }, name: "Bold" },
  ]);

  fireEvent.click(screen.getByRole("button", { name: "Remove style 1" }));
  expect(useStore.getState().form.styles).toEqual([{ axes: { wght: "675" }, name: "Bold" }]);
  expect(screen.queryByRole("group", { name: "Style 2" })).toBeNull();
});

test("a feature that swaps characters shows them, with a larger view on demand", () => {
  withFonts({});
  useStore.setState({ fonts: useStore.getState().fonts.map((f) => ({ ...f, face: "fontmint-preview-1" })) });
  render(<Options />);
  // ss01 swaps 0 and I (test/fonts.ts); ss02 lists no single characters.
  expect(screen.getByRole("button", { name: "Show what Slashed zero changes" }).textContent).toBe("0I0I");
  expect(screen.queryByRole("button", { name: "Show what Stylistic set 2 changes" })).toBeNull();
});
