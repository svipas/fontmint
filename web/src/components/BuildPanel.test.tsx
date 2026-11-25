import { beforeEach, expect, test } from "bun:test";
import { act, render, screen } from "@testing-library/react";
import { resetStore, withFonts } from "../../test/store";
import { emptyForm } from "../lib/options";
import { useStore } from "../store";
import { BuildPanel } from "./BuildPanel";
import { FontList } from "./FontList";

beforeEach(resetStore);

const buildButton = () => screen.getByRole("button", { name: /Build fonts/ }) as HTMLButtonElement;

test("Build waits for a name", () => {
  withFonts({});
  render(<BuildPanel />);
  expect(buildButton().disabled).toBe(true);
  act(() => useStore.setState({ form: { ...emptyForm, name: "Mint Sans" } }));
  expect(buildButton().disabled).toBe(false);
});

test("the missing name takes you to its field", () => {
  withFonts({});
  render(
    <>
      <input id="name" aria-label="New family name" />
      <BuildPanel />
    </>,
  );
  act(() => screen.getByRole("button", { name: "Give your build a family name to start." }).click());
  expect(document.activeElement).toBe(screen.getByLabelText("New family name"));
});

test("Build waits until every font is read", () => {
  withFonts({});
  useStore.setState({
    form: { ...emptyForm, name: "Mint Sans" },
    fonts: [{ ...useStore.getState().fonts[0]!, info: null }],
  });
  render(<BuildPanel />);
  expect(buildButton().disabled).toBe(true);
});

test("fontmint's errors are shown as they are; other errors ask for a bug report", () => {
  withFonts({});
  const message = "Font0.ttf: --line-height 9 is out of range; use a multiple of the font size between 0.5 and 3";
  useStore.setState({ build: { status: "failed", error: message, user: true } });
  render(<BuildPanel />);
  expect(screen.getByRole("alert").textContent).toContain(message);
  expect(screen.queryByText(/Please report it/)).toBeNull();

  act(() => useStore.setState({ build: { status: "failed", error: "TypeError: x is undefined", user: false } }));
  expect(screen.getByText(/Please report it/)).toBeTruthy();
});

test("progress, warnings and the log while building", () => {
  withFonts({});
  useStore.setState({
    build: { status: "running", stage: "building", done: 4, total: 18, left: 33 },
    warnings: ["Font0.ttf: no --name given"],
    log: [{ text: "Font0.ttf: froze ss02: 50 characters remapped", warning: false }],
  });
  render(<BuildPanel />);
  expect(screen.getByText(/4 of 18 fonts · about 33 s left/)).toBeTruthy();
  expect(screen.getByRole("progressbar", { name: "Build progress" }).getAttribute("aria-valuenow")).toBe("22");
  expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
  expect(screen.getByText("Font0.ttf: no --name given")).toBeTruthy();
  expect(screen.getByText(/froze ss02: 50 characters remapped/)).toBeTruthy();
});

test("the finished build offers its zip", () => {
  withFonts({});
  useStore.setState({
    form: { ...emptyForm, name: "Mint Sans" },
    build: { status: "done", url: "blob:zip", fileName: "MintSans.zip", size: 3 * 2 ** 20, files: 20, seconds: 44 },
  });
  render(<BuildPanel />);
  const link = screen.getByRole("link", { name: /Download MintSans.zip · 3.0 MB/ });
  expect(link.getAttribute("download")).toBe("MintSans.zip");
  expect(screen.getByText(/Built 20 font files in 44 s\./)).toBeTruthy();
});

test("names from a font are shown as text, never as HTML", () => {
  withFonts({ family: '<img src=x onerror="alert(1)">' });
  render(<FontList />);
  expect(screen.getByText('<img src=x onerror="alert(1)">')).toBeTruthy();
  expect(document.querySelector("img")).toBeNull();
});

test("fonts from different families get a warning", () => {
  withFonts({ family: "Inter Variable" }, { family: "Inter", italic: true });
  const { unmount } = render(<FontList />);
  expect(screen.queryByText(/families/)).toBeNull();
  unmount();
  withFonts({ family: "Inter Variable" }, { family: "JetBrains Mono" });
  render(<FontList />);
  expect(screen.getByText("Fonts from 2 families")).toBeTruthy();
  expect(screen.getByText(/Inter and JetBrains Mono would all get the same name/)).toBeTruthy();
});
