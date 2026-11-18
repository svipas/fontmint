// The production build in a real browser, with real Pyodide, on the test fonts from
// tests/fixtures.py (a variable upright and italic with wght and wdth, ss01 "Slashed
// zero", and a static font).
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, type Page, test } from "@playwright/test";
import { writeFixtureFonts } from "../test/fixture-fonts";
import { zipNames } from "./zip";

const folder = mkdtempSync(join(tmpdir(), "fontmint-e2e-"));
const fonts = writeFixtureFonts(folder);
test.afterAll(() => rmSync(folder, { recursive: true, force: true }));

async function addFonts(page: Page, ...paths: string[]) {
  await page.goto("./");
  await page.locator('input[type="file"]').setInputFiles(paths);
}

const buildButton = (page: Page) => page.getByRole("button", { name: "Build fonts" });
const nameField = (page: Page) => page.getByRole("textbox", { name: "New family name" });

test("freeze a feature, rename and download the family", async ({ page }) => {
  await addFonts(page, fonts.variable, fonts.italic);
  await expect(page.getByText("TestSans-Italic[wght,wdth].ttf", { exact: true })).toBeVisible();

  await page.getByText("Slashed zero").click();
  const preview = page.getByRole("textbox", { name: "Preview text with your changes" });
  await expect(preview).toHaveCSS("font-feature-settings", /"ss01"/);
  expect(await page.evaluate(() => CSS.highlights.get("fontmint-changed")?.size)).toBeGreaterThan(0);

  await nameField(page).fill("Mint Sans");
  await buildButton(page).click();
  const download = page.getByRole("link", { name: /Download MintSans\.zip/ });
  await expect(download).toBeVisible();
  await expect(page.getByText(/Built 20 files in/)).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Preview text in your build" })).toBeVisible();

  const [file] = await Promise.all([page.waitForEvent("download"), download.click()]);
  const names = zipNames(readFileSync(await file.path()));
  expect(names).toContain("MintSans/variable/MintSans[wght,wdth].ttf");
  expect(names).toContain("MintSans/variable/MintSans-Italic[wght,wdth].woff2");
  expect(names).toContain("MintSans/ttf-unhinted/MintSans-BoldItalic.ttf");
  expect(names).toHaveLength(20);
});

test("fonts added together appear together, upright first", async ({ page }) => {
  // The italic first, as a file picker hands them over.
  await addFonts(page, fonts.italic, fonts.variable);
  // The moment any font's details show, none is still being read: the page changes once.
  const state = await page.waitForFunction(() => {
    const rows = [...document.querySelectorAll('li:has(button[aria-label^="Remove"])')];
    const reading = rows.filter((row) => row.textContent?.includes("Reading font…")).length;
    return reading < rows.length ? { reading } : null;
  });
  expect(await state.jsonValue()).toEqual({ reading: 0 });
  await expect(page.getByRole("listitem").filter({ hasText: ".ttf" }).first()).toContainText("TestSans[wght,wdth].ttf");
});

test("one static font at weight 375, named Book", async ({ page }) => {
  await addFonts(page, fonts.variable);
  await nameField(page).fill("Mint Sans");
  await page.getByRole("button", { name: "Axis values and style name" }).click();
  await page.getByRole("textbox", { name: /Weight/ }).fill("375");
  await page.getByRole("textbox", { name: "Style name" }).fill("Book");
  await page.getByText("WOFF2", { exact: true }).click();
  await buildButton(page).click();

  await expect(page.getByText(/Built 1 file in/)).toBeVisible();
  await expect(page.getByLabel("Build log")).toContainText("MintSans-Book (wght 375");

  // The button in the pinned bar takes you down to the log.
  await page.mouse.wheel(0, -5000);
  await page.getByRole("button", { name: /^(Build log|\d+ warnings?)$/ }).click();
  await expect(page.locator("#build-log")).toBeFocused();
  await expect(page.locator("#build-log")).toBeInViewport();
});

test("two named static fonts in one build", async ({ page }) => {
  await addFonts(page, fonts.variable);
  await nameField(page).fill("Mint Sans");
  await page.getByRole("button", { name: "Axis values and style names" }).click();
  await page.getByRole("textbox", { name: /Weight/ }).fill("375");
  await page.getByRole("textbox", { name: "Style name" }).fill("Regular");
  await page.getByRole("button", { name: "Add another style" }).click();
  const second = page.getByRole("group", { name: "Style 2" });
  await second.getByRole("textbox", { name: /Weight/ }).fill("675");
  await second.getByRole("textbox", { name: "Style name" }).fill("Bold");
  await buildButton(page).click();

  await expect(page.getByText(/Built 4 files in/)).toBeVisible();
  const log = page.getByLabel("Build log");
  await expect(log).toContainText("MintSans-Regular (wght 375");
  await expect(log).toContainText("MintSans-Bold (wght 675");
});

test("fields are checked as you type", async ({ page }) => {
  await addFonts(page, fonts.variable);
  await expect(nameField(page)).toHaveValue("Test Sans Custom");
  await expect(buildButton(page)).toBeEnabled();
  await nameField(page).fill("");
  await expect(page.getByText(/Give your build its own name/)).toBeVisible();
  await expect(buildButton(page)).toBeDisabled();
  await nameField(page).fill("Mint/Sans");
  await expect(page.getByText(/can only use ASCII letters/)).toBeVisible();
  await expect(buildButton(page)).toBeDisabled();
  await nameField(page).fill("Mint Sans");
  await expect(buildButton(page)).toBeEnabled();
});

test("the message by Build takes you to the field to fix", async ({ page }) => {
  await addFonts(page, fonts.variable);
  await nameField(page).fill("");
  await page.mouse.wheel(0, 2000);
  await page.getByRole("button", { name: "Give your build a family name to start." }).click();
  await expect(nameField(page)).toBeFocused();
  await expect(nameField(page)).toBeInViewport();

  await page.keyboard.type("Mint/Sans");
  await page.mouse.wheel(0, 2000);
  await page.getByRole("button", { name: "Fix the marked field to build." }).click();
  await expect(nameField(page)).toBeFocused();
  await expect(nameField(page)).toBeInViewport();
});

test("a build can be cancelled", async ({ page }) => {
  // Two fonts build on two workers. The second one starts loading Pyodide only when the
  // build starts, and never gets it here, so the build is still running at Cancel.
  await page.addInitScript(() => Object.defineProperty(navigator, "hardwareConcurrency", { get: () => 4 }));
  await addFonts(page, fonts.variable, fonts.italic);
  await nameField(page).fill("Mint Sans");
  await expect(buildButton(page)).toBeEnabled();
  await page.route("**/pyodide.asm.wasm", () => {});
  await buildButton(page).click();
  await page.getByRole("button", { name: "Cancel" }).click();
  await expect(buildButton(page)).toBeEnabled();
  await expect(page.getByRole("link", { name: /Download/ })).toHaveCount(0);
});

test("a file that isn't a font says so", async ({ page }) => {
  const broken = join(folder, "Broken.ttf");
  writeFileSync(broken, "not a font");
  await addFonts(page, broken);
  await expect(page.getByText(/not a readable font/)).toBeVisible();
  await expect(page.getByText("Remove the file that couldn't be read to build.")).toBeVisible();
});

test("a dropped file is added once", async ({ page }) => {
  await page.goto("./");
  // The drop area sits inside the page, which takes drops too.
  await page.getByRole("region", { name: "Add fonts" }).evaluate((area) => {
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(new File(["not a font"], "Dropped.ttf"));
    area.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer }));
  });
  await expect(page.getByText(/not a readable font/)).toBeVisible();
  await expect(page.getByRole("listitem")).toHaveCount(1);
});

test("the theme choice is kept", async ({ page }) => {
  await page.goto("./");
  await page.getByRole("button", { name: "Dark" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Light" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});

test("static input passes through as one file", async ({ page }) => {
  await addFonts(page, fonts.static);
  await nameField(page).fill("Mint Sans");
  await buildButton(page).click();
  await expect(page.getByText(/Built 1 file in/)).toBeVisible();
});

test("the page stays put as the preview changes", async ({ page }) => {
  await addFonts(page, fonts.variable);
  const preview = page.getByRole("textbox", { name: "Preview text with your changes" });
  const top = async (locator: typeof preview) => (await locator.boundingBox())!.y;
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    const before = await top(preview);
    await page.getByLabel("wght", { exact: true }).press("ArrowRight");
    await expect(page.getByRole("button", { name: "Reset size and axes" })).toBeVisible();
    expect(await top(preview)).toBe(before);
    await page.getByRole("button", { name: "Reset size and axes" }).click();
  }

  await page.setViewportSize({ width: 1280, height: 900 });
  const name = nameField(page);
  const before = await top(name);
  await page.getByLabel("Size", { exact: true }).press("End");
  expect(await top(name)).toBe(before);
});
