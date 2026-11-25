import { beforeEach, expect, test } from "bun:test";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { resetStore, setState, withFonts } from "../../test/store";
import { store } from "../store";
import { Preview } from "./Preview";

beforeEach(resetStore);

const reset = () => screen.queryByRole("button", { name: "Reset size and axes" });

function withLoadedFonts(...infos: Parameters<typeof withFonts>) {
  withFonts(...infos);
  setState({
    fonts: store.state.fonts.map((f, i) => ({ ...f, face: `fontmint-preview-${i}` })),
    previewAxes: { wght: 400, wdth: 100 },
  });
}

test("moved axes go back to the font's defaults", () => {
  withLoadedFonts({});
  render(<Preview />);
  expect(reset()).toBeNull();

  act(() => store.actions.setPreviewAxis("wght", 900));
  expect(screen.getByText("900")).toBeTruthy();
  fireEvent.click(reset()!);
  expect(store.state.previewAxes).toEqual({ wght: 400, wdth: 100 });
  expect(reset()).toBeNull();
  expect(document.activeElement?.getAttribute("type")).toBe("range");
});

test("the size goes back too", () => {
  withLoadedFonts({});
  render(<Preview />);
  fireEvent.change(screen.getByLabelText("Size"), { target: { value: "40" } });
  expect(screen.getByText("40px")).toBeTruthy();
  fireEvent.click(reset()!);
  expect(screen.getByText("28px")).toBeTruthy();
  expect(reset()).toBeNull();
});
