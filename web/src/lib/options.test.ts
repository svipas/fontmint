import { describe, expect, test } from "bun:test";
import { fontInfo } from "../../test/fonts";
import { cliCommands, emptyForm, type Form, formErrors, type Style, shellQuote, webOptions } from "./options";

const one = (...args: Parameters<typeof cliCommands>) => cliCommands(...args).join("\n");
/** A form with one custom style from `axes` and `styleName`, the way most tests need it. */
const form = ({
  axes = {},
  styleName = "",
  ...change
}: Partial<Form> & { axes?: Record<string, string>; styleName?: string } = {}): Form => ({
  ...emptyForm,
  name: "Mint Sans",
  styles: [{ axes, name: styleName }],
  ...change,
});

describe("webOptions", () => {
  test("variable TrueType font: TTF + WOFF2, its axes, no unset values", () => {
    const options = webOptions(form({ freeze: ["ss01"], axes: { wght: " 400,700 ", wdth: "" } }), fontInfo());
    expect(options).toEqual({
      name: "Mint Sans",
      features: "ss01",
      language: "",
      disable: "",
      letter_spacing: 0,
      subset: "",
      formats: ["ttf", "woff2"],
      static: true,
      axes: { wght: "400,700" },
      style_name: "",
    });
    expect("line_height" in options).toBe(false);
  });

  test("CFF2 variable font is written as OTF", () => {
    expect(webOptions(form(), fontInfo({ cff2: true })).formats).toEqual(["otf", "woff2"]);
    expect(webOptions(form({ formats: { own: true, woff2: false } }), fontInfo({ cff2: true })).formats).toEqual([
      "otf",
    ]);
  });

  test("static font gets no output options", () => {
    const options = webOptions(form({ axes: { wght: "400" } }), fontInfo({ variable: false, axes: [] }));
    expect(options.formats).toBeUndefined();
    expect(options.axes).toBeUndefined();
    expect(options.static).toBeUndefined();
  });

  test("each font only gets the features and language it has", () => {
    const italic = fontInfo({ features: ["calt", "ss01"], positioning: ["kern"], languages: [] });
    const options = webOptions(
      form({ freeze: ["ss01", "ss02"], disable: ["calt", "liga", "kern"], language: "ROM" }),
      italic,
    );
    expect(options.features).toBe("ss01");
    expect(options.disable).toBe("calt,kern");
    expect(options.language).toBe("");
  });

  test("several custom styles are sent as a list; empty rows are left out", () => {
    const styles: Style[] = [
      { axes: { wght: "375" }, name: "Regular" },
      { axes: {}, name: "" },
      { axes: { wght: "675", wdth: " " }, name: "Bold" },
    ];
    const options = webOptions(form({ styles }), fontInfo());
    expect(options.styles).toEqual([
      { axes: { wght: "375" }, style_name: "Regular" },
      { axes: { wght: "675" }, style_name: "Bold" },
    ]);
    expect("axes" in options || "style_name" in options).toBe(false);
  });

  test("a language is left out for a font with nothing to freeze", () => {
    const options = webOptions({ ...emptyForm, language: "ROM" }, fontInfo({ features: ["liga"] }));
    expect([options.features, options.language]).toEqual(["", ""]);
  });

  test("a language freezes locl", () => {
    const options = webOptions(form({ language: "ROM" }), fontInfo({ features: ["locl"] }));
    expect([options.features, options.language]).toEqual(["locl", "ROM"]);
  });

  test("numbers and subsets", () => {
    const options = webOptions(
      form({ lineHeight: "1.4", letterSpacing: "-0.02", subset: ["latin"], subsetRanges: "U+2190-21FF, U+20AC" }),
      fontInfo(),
    );
    expect([options.line_height, options.letter_spacing, options.subset]).toEqual([
      1.4,
      -0.02,
      "latin,U+2190-21FF,U+20AC",
    ]);
  });
});

describe("formErrors", () => {
  const variable = [fontInfo()];

  test("a name is required, in characters fontmint accepts", () => {
    expect(formErrors({ ...emptyForm }).name).toContain("own name");
    expect(formErrors(form()).name).toBeUndefined();
    expect(formErrors(form({ name: "Mint/Sans" })).name).toContain("found /");
    expect(formErrors(form({ name: "Mint Süß" })).name).toContain("found ü ß");
    expect(formErrors(form({ name: " . " })).name).toContain("letters or digits");
  });

  test("numbers in fontmint's ranges", () => {
    const errors = formErrors(form({ lineHeight: "tall", letterSpacing: "1,5" }));
    expect(errors.lineHeight).toContain("Enter a number");
    expect(errors.letterSpacing).toContain("Enter a number");
    expect(formErrors(form({ lineHeight: "9" })).lineHeight).toBe("Use a value from 0.5 to 3");
    expect(formErrors(form({ lineHeight: "1.4", letterSpacing: "-0.02" }))).toEqual({});
  });

  test("character ranges", () => {
    expect(formErrors(form({ subsetRanges: "U+2190-21FF, U+20AC" })).subsetRanges).toBeUndefined();
    expect(formErrors(form({ subsetRanges: "U+20AC, euro" })).subsetRanges).toContain('"euro"');
    expect(formErrors(form({ subsetRanges: "U+21FF-2190" })).subsetRanges).toContain("U+21FF-2190");
    expect(formErrors(form({ subsetRanges: "U+110000" })).subsetRanges).toContain("U+110000");
  });

  test("formats, only for variable fonts", () => {
    const none = form({ formats: { own: false, woff2: false } });
    expect(formErrors(none, variable).formats).toBe("Choose at least one format.");
    expect(formErrors(none, [fontInfo({ variable: false, axes: [] })]).formats).toBeUndefined();
  });

  test("axis values: syntax and the font's range", () => {
    expect(formErrors(form({ axes: { wght: "300:700, 375, all" } }), variable)).toEqual({});
    expect(formErrors(form({ axes: { wght: "bold" } }), variable)["axis-0-wght"]).toContain('"bold" isn\'t a value');
    expect(formErrors(form({ axes: { wght: "50" } }), variable)["axis-0-wght"]).toBe(
      "50 is outside this font's range, 100–900",
    );
    expect(formErrors(form({ axes: { wght: "300:" } }), variable)["axis-0-wght"]).toBeDefined();
  });

  test("single values need static fonts", () => {
    const errors = formErrors(form({ staticFonts: false, axes: { wght: "375" } }), variable);
    expect(errors.staticFonts).toContain("make static fonts");
    expect(formErrors(form({ staticFonts: false, axes: { wght: "300:700" } }), variable)).toEqual({});
  });

  test("each custom style is checked by its row", () => {
    const styles: Style[] = [
      { axes: { wght: "375" }, name: "Regular" },
      { axes: { wght: "1200" }, name: "Bold" },
      { axes: { wght: "400,700" }, name: "Black" },
    ];
    const errors = formErrors(form({ styles }), variable);
    expect(Object.keys(errors)).toEqual(["axis-1-wght", "style-2"]);
  });

  test("a style name needs exactly one static font", () => {
    expect(formErrors(form({ styleName: "Book", axes: { wght: "375" } }), variable)).toEqual({});
    expect(formErrors(form({ styleName: "Book" }), variable)["style-0"]).toContain("this builds 2");
    expect(formErrors(form({ styleName: "Book", axes: { wght: "375,700" } }), variable)["style-0"]).toContain(
      "this builds 2",
    );
    // A range keeps the font variable: no static font to name.
    expect(
      formErrors(form({ styleName: "Book", axes: { wght: "375", wdth: "75:100" } }), variable)["style-0"],
    ).toContain("this builds 0");
    expect(formErrors(form({ styleName: "B/k", axes: { wght: "375" } }), variable)["style-0"]).toContain("found /");
    // A bad axis value has its own error; the style name waits for it.
    expect(formErrors(form({ styleName: "Book", axes: { wght: "375, 1200" } }), variable)["style-0"]).toBeUndefined();
  });
});

describe("cliCommands", () => {
  test("fonts with different features get a command each, with only their own", () => {
    const upright = fontInfo();
    const italic = fontInfo({ features: ["ss01"], italic: true });
    const both = form({ freeze: ["ss01", "ss02"] });
    expect(cliCommands(["A.ttf", "A-Italic.ttf"], form({ freeze: ["ss01"] }), [upright, italic])).toEqual([
      "fontmint A.ttf A-Italic.ttf --features ss01 --name 'Mint Sans'",
    ]);
    expect(cliCommands(["A.ttf", "A-Italic.ttf"], both, [upright, italic])).toEqual([
      "fontmint A.ttf --features ss01,ss02 --name 'Mint Sans'",
      "fontmint A-Italic.ttf --features ss01 --name 'Mint Sans'",
    ]);
  });

  test("each custom style is a command of its own", () => {
    const styles: Style[] = [
      { axes: { wght: "375" }, name: "Regular" },
      { axes: { wght: " 675 " }, name: "Bold" },
      { axes: {}, name: " " },
    ];
    expect(cliCommands(["A.ttf", "B.ttf"], form({ styles }), [fontInfo(), fontInfo({ variable: false })])).toEqual([
      "fontmint A.ttf --name 'Mint Sans' --weight 375 --style-name Regular",
      "fontmint B.ttf --name 'Mint Sans'",
      "fontmint A.ttf --name 'Mint Sans' --weight 675 --style-name Bold",
    ]);
  });

  test("axis values only go to variable fonts", () => {
    const fonts = [fontInfo(), fontInfo({ variable: false, axes: [], instances: [] })];
    expect(cliCommands(["A.ttf", "B.ttf"], form({ axes: { wght: "375" } }), fonts)).toEqual([
      "fontmint A.ttf --name 'Mint Sans' --weight 375",
      "fontmint B.ttf --name 'Mint Sans'",
    ]);
  });

  test("the same build, quoted for a shell", () => {
    const [command] = cliCommands(
      ["Test Sans[wght,wdth].ttf"],
      form({ name: "Mint Sans", freeze: ["ss01"], disable: ["calt"], axes: { wght: "300:700", XHGT: "1" } }),
      [fontInfo()],
    );
    expect(command).toBe(
      "fontmint 'Test Sans[wght,wdth].ttf' --features ss01 --disable calt --name 'Mint Sans' --weight 300:700 --axis XHGT=1",
    );
  });

  test("leaves out --formats when both are chosen, so the CLI builds everything", () => {
    expect(one(["A.ttf"], form(), [fontInfo()])).not.toContain("--formats");
    expect(one(["A.ttf"], form({ formats: { own: false, woff2: true } }), [fontInfo()])).toContain("--formats woff2");
    expect(one(["A.otf"], form({ formats: { own: true, woff2: false } }), [fontInfo({ cff2: true })])).toContain(
      "--formats otf",
    );
  });

  test("--no-static, and no output options for static fonts", () => {
    expect(one(["A.ttf"], form({ staticFonts: false }), [fontInfo()])).toContain("--no-static");
    expect(one(["A.ttf"], form({ staticFonts: false }), [fontInfo({ variable: false })])).toBe(
      "fontmint A.ttf --name 'Mint Sans'",
    );
  });
});

test("shellQuote", () => {
  expect(shellQuote("Inter.ttf")).toBe("Inter.ttf");
  expect(shellQuote("it's here")).toBe(`'it'\\''s here'`);
  expect(shellQuote("$(rm -rf ~)")).toBe("'$(rm -rf ~)'");
});
