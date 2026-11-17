// The page's form: its state, the options it sends to each font, and the same build as a
// fontmint command.
import type { Format, FontInfo, WebOptions } from "./types";

export const SUBSETS = ["latin", "latin-ext", "cyrillic", "cyrillic-ext", "greek", "vietnamese"] as const;

export type Form = {
  name: string;
  freeze: string[];
  disable: string[];
  /** OpenType language tag whose forms to freeze (adds locl), or "". */
  language: string;
  /** As typed; "" leaves the font's own value. */
  lineHeight: string;
  letterSpacing: string;
  subset: string[];
  /** Extra subset ranges as typed, e.g. "U+2190-21FF". */
  subsetRanges: string;
  /** Variable input only. */
  formats: { own: boolean; woff2: boolean };
  staticFonts: boolean;
  /** Custom styles; a row with nothing in it changes nothing. Variable input only. */
  styles: Style[];
};

/** One custom style: axis values, and a name for the one static font they make. */
export type Style = {
  /** Axis tag → values as typed ("400,700", "300:700", "all"). */
  axes: Record<string, string>;
  name: string;
};

export const emptyStyle: Style = { axes: {}, name: "" };

export const emptyForm: Form = {
  name: "",
  freeze: [],
  disable: [],
  language: "",
  lineHeight: "",
  letterSpacing: "",
  subset: [],
  subsetRanges: "",
  formats: { own: true, woff2: true },
  staticFonts: true,
  styles: [emptyStyle],
};

export type Field =
  | "name"
  | "lineHeight"
  | "letterSpacing"
  | "subsetRanges"
  | "formats"
  | "staticFonts"
  /** By the style's row: `axis-0-wght`, `style-0`. */
  | `axis-${number}-${string}`
  | `style-${number}`;
export type FormErrors = Partial<Record<Field, string>>;

// fontmint's own limits (metrics.py, naming.py, subset.py); it checks again when building.
const LINE_HEIGHT = [0.5, 3] as const;
const LETTER_SPACING = [-0.5, 1] as const;
const FORBIDDEN = new Set('[](){}<>/%\\:*?"|');
const RANGE = /^U\+([0-9A-F]{1,6})(?:-([0-9A-F]{1,6}))?$/i;

/** Problems with a name, as fontmint's check_name() sees them. */
function nameError(value: string, what: string): string | undefined {
  const bad = [...new Set([...value].filter((c) => c !== " " && (c < "!" || c > "~" || FORBIDDEN.has(c))))];
  if (bad.length)
    return `${what} can only use ASCII letters, digits, spaces and punctuation other than ${[...FORBIDDEN].join("")} (found ${bad.join(" ")})`;
  if (!value.replaceAll(" ", "").replaceAll(".", "")) return `${what} needs letters or digits`;
}

function numberError(text: string, [low, high]: readonly [number, number], example: string): string | undefined {
  if (!text.trim()) return;
  const value = Number(text);
  if (!Number.isFinite(value)) return `Enter a number, e.g. ${example}`;
  if (value < low || value > high) return `Use a value from ${low} to ${high}`;
}

type AxisItem = number | [number, number] | "all";

/** An axis field as fontmint's axes.parse_spec() reads it, or an error. */
function parseAxis(text: string, [min, max]: [number, number]): AxisItem[] | string {
  const items = text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const parsed: AxisItem[] = [];
  for (const item of items) {
    if (item === "all") {
      parsed.push("all");
      continue;
    }
    const parts = item.split(":");
    const values = parts.map((part) => (part.trim() ? Number(part) : Number.NaN));
    if (parts.length > 2 || values.some((value) => !Number.isFinite(value)))
      return `"${item}" isn't a value: use numbers like 400, ranges like 300:700, or "all"`;
    const outside = values.find((value) => value < min || value > max);
    if (outside !== undefined) return `${outside} is outside this font's range, ${min}–${max}`;
    const [low, high] = [Math.min(...values), Math.max(...values)] as [number, number];
    parsed.push(low === high ? low : [low, high]);
  }
  return parsed;
}

/** Axis tag → [min, max], from the first font that has the axis. */
export function axisRanges(infos: FontInfo[]): Map<string, [number, number]> {
  const axes = new Map<string, [number, number]>();
  for (const info of infos) for (const [tag, min, , max] of info.axes) if (!axes.has(tag)) axes.set(tag, [min, max]);
  return axes;
}

/** How many static fonts the axis fields make for one font: single values multiply;
 * no values at all means one per named style. */
function staticCount(form: Form, info: FontInfo, parsed: Map<string, AxisItem[]>): number {
  if (!form.staticFonts) return 0;
  if (!parsed.size) return info.instances.length;
  let count = 1;
  for (const [tag, items] of parsed) {
    const singles = new Set<number>();
    for (const item of items) {
      if (typeof item === "number") singles.add(item);
      else if (item === "all") for (const [, at] of info.instances) if (at[tag] !== undefined) singles.add(at[tag]);
    }
    count *= singles.size;
  }
  return count;
}

/** Problems the page can show while the user types, by field. fontmint checks everything
 * again when building; these mirror its rules so most mistakes never get that far. */
export function formErrors(form: Form, infos: FontInfo[] = []): FormErrors {
  const errors: FormErrors = {};
  const name = form.name.trim();
  if (!name) errors.name = "Give your build its own name, so it never passes as the original font.";
  else errors.name = nameError(name, "The name");
  errors.lineHeight = numberError(form.lineHeight, LINE_HEIGHT, "1.4");
  errors.letterSpacing = numberError(form.letterSpacing, LETTER_SPACING, "0.02");
  for (const item of form.subsetRanges.split(/[\s,]+/).filter(Boolean)) {
    const match = RANGE.exec(item);
    const first = match ? Number.parseInt(match[1]!, 16) : 0;
    const last = match?.[2] ? Number.parseInt(match[2], 16) : first;
    if (!match || first > last || last > 0x10ffff) {
      errors.subsetRanges = `"${item}" isn't a character range; write ranges like U+2190-21FF or U+20AC`;
      break;
    }
  }

  const variable = infos.filter((info) => info.variable);
  if (variable.length) {
    if (!form.formats.own && !form.formats.woff2) errors.formats = "Choose at least one format.";
    const ranges = axisRanges(variable);
    form.styles.forEach((style, row) => {
      const parsed = new Map<string, AxisItem[]>();
      let readable = true;
      for (const [tag, range] of ranges) {
        const text = style.axes[tag]?.trim();
        if (!text) continue;
        const result = parseAxis(text, range);
        if (typeof result === "string") {
          errors[`axis-${row}-${tag}`] = result;
          readable = false;
        } else parsed.set(tag, result);
      }
      const singles = [...parsed.values()].some((items) => items.some((item) => !Array.isArray(item)));
      if (!form.staticFonts && singles)
        errors.staticFonts = 'Single values and "all" make static fonts: turn this on, or give ranges like 300:700.';
      const styleName = style.name.trim();
      // The count needs every axis field readable; a bad one already shows its own error.
      if (styleName && readable) {
        const counts = variable.filter((info) => !info.cff2).map((info) => staticCount(form, info, parsed));
        if (counts.some((count) => count !== 1))
          errors[`style-${row}`] =
            `A style name needs exactly one static font per input; this builds ${Math.max(...counts, 0)}. Give each axis a single value.`;
        else errors[`style-${row}`] = nameError(styleName, "The style name");
      }
    });
  }
  for (const key of Object.keys(errors) as Field[]) if (!errors[key]) delete errors[key];
  return errors;
}

/** The custom styles with something in them, as fontmint takes them. */
function customStyles(form: Form): { axes: Record<string, string>; style_name: string }[] {
  return form.styles
    .map((style) => ({
      axes: Object.fromEntries(
        Object.entries(style.axes)
          .map(([tag, value]) => [tag, value.trim()])
          .filter(([, value]) => value),
      ) as Record<string, string>,
      style_name: style.name.trim(),
    }))
    .filter((style) => style.style_name || Object.keys(style.axes).length);
}

function subsetSpec(form: Form): string {
  return [...form.subset, ...form.subsetRanges.split(/[\s,]+/).filter(Boolean)].join(",");
}

function freezeTags(form: Form): string[] {
  return form.language && !form.freeze.includes("locl") ? [...form.freeze, "locl"] : form.freeze;
}

/** What one font gets: only the features and language it has, since fontmint rejects
 * the others (an italic may lack a feature its upright has). A language needs a feature
 * to freeze, so it's left out when the font has none of them. */
export function webOptions(form: Form, info: FontInfo): WebOptions {
  const has = new Set([...info.features, ...info.positioning]);
  const hasLanguage = info.languages.includes(form.language);
  const freeze = freezeTags({ ...form, language: hasLanguage ? form.language : "" }).filter((tag) => has.has(tag));
  const language = hasLanguage && freeze.length ? form.language : "";
  const options: WebOptions = {
    name: form.name.trim(),
    features: freeze.join(","),
    language,
    disable: form.disable.filter((tag) => has.has(tag)).join(","),
    letter_spacing: form.letterSpacing.trim() ? Number(form.letterSpacing) : 0,
    subset: subsetSpec(form),
  };
  if (form.lineHeight.trim()) options.line_height = Number(form.lineHeight);
  if (info.variable) {
    const own: Format = info.cff2 ? "otf" : "ttf";
    options.formats = [...(form.formats.own ? [own] : []), ...(form.formats.woff2 ? (["woff2"] as const) : [])];
    options.static = form.staticFonts;
    const styles = customStyles(form);
    // One style is fontmint's own axis options; several are built one after the other.
    if (styles.length > 1) options.styles = styles;
    else {
      options.axes = styles[0]?.axes ?? {};
      options.style_name = styles[0]?.style_name ?? "";
    }
  }
  return options;
}

const AXIS_FLAGS: Record<string, string> = {
  wght: "--weight",
  wdth: "--width",
  slnt: "--slant",
  ital: "--italic",
  opsz: "--optical-size",
};

/** A word for a POSIX shell: as it is when that's safe, otherwise in single quotes. */
export function shellQuote(word: string): string {
  return /^[\w.,:=+@%/-]+$/.test(word) ? word : `'${word.replaceAll("'", `'\\''`)}'`;
}

/** The same build as fontmint commands: one for all fonts when they take the same options,
 * otherwise one per group that does. Like the page, a font only gets the features and
 * language it has - the command line rejects the others - and only variable fonts get
 * output options. Each custom style is a command of its own, as --style-name names one
 * static font per run. --formats is left out when both web formats are chosen, so the
 * command line builds everything it can, hinted fonts and OTF included. `files[i]` is `fonts[i]`. */
export function cliCommands(files: string[], form: Form, fonts: FontInfo[]): string[] {
  const groups = new Map<string, { files: string[]; args: string[] }>();
  const styles = customStyles(form);
  for (const [row, style] of (styles.length ? styles : [undefined]).entries()) {
    fonts.forEach((info, i) => {
      if (!info.variable && row > 0) return; // static input is built once, whatever the styles
      const args = cliArgs(form, info, style);
      const key = args.join(" ");
      const group = groups.get(key) ?? { files: [], args };
      groups.set(key, group);
      group.files.push(shellQuote(files[i]!));
    });
  }
  return [...groups.values()].map((group) => ["fontmint", ...group.files, ...group.args].join(" "));
}

function cliArgs(form: Form, info: FontInfo, style?: { axes: Record<string, string>; style_name: string }): string[] {
  const args: string[] = [];
  const add = (flag: string, value: string) => value && args.push(flag, shellQuote(value));
  const { features = "", language = "", disable = "" } = webOptions(form, info);
  add("--features", features);
  add("--language", language);
  add("--disable", disable);
  add("--line-height", form.lineHeight.trim());
  add("--letter-spacing", form.letterSpacing.trim());
  add("--subset", subsetSpec(form));
  add("--name", form.name.trim());
  if (info.variable) {
    for (const [tag, value] of Object.entries(style?.axes ?? {})) {
      if (AXIS_FLAGS[tag]) add(AXIS_FLAGS[tag], value);
      else add("--axis", `${tag}=${value}`);
    }
    add("--style-name", style?.style_name ?? "");
    if (form.formats.own !== form.formats.woff2)
      add("--formats", form.formats.woff2 ? "woff2" : info.cff2 ? "otf" : "ttf");
    if (!form.staticFonts) args.push("--no-static");
  }
  return args;
}
