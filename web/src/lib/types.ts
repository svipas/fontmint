// Values that cross between the page, its workers and Python (web/fontmint_web.py).

export type Manifest = {
  /** The website's version (web/package.json). */
  site: string;
  pyodide: string;
  /** The version of the fontmint wheel the site runs; the core may be ahead of that release. */
  fontmint: string;
  /** Short git commit the site was built from. */
  commit: string;
  wheels: string[];
  /** Bytes of every file a worker fetches while starting, for download progress. */
  downloads: Record<string, number>;
};

/** core.FontInfo, plus whether the font has CFF2 outlines and the characters each feature swaps. */
export type FontInfo = {
  family: string;
  variable: boolean;
  cff2: boolean;
  axes: [tag: string, min: number, defaultValue: number, max: number][];
  instances: [style: string, coordinates: Record<string, number>][];
  /** Substitution (GSUB) feature tags. */
  features: string[];
  /** Positioning (GPOS) feature tags. */
  positioning: string[];
  feature_names: Record<string, string>;
  languages: string[];
  italic: boolean;
  line_height: number;
  /** Feature tag → code points whose glyph freezing it swaps. */
  changes: Record<string, number[]>;
};

/** fontmint's Options as the page sends them; see web_options() in fontmint_web.py. */
export type WebOptions = {
  features?: string;
  language?: string;
  disable?: string;
  line_height?: number;
  letter_spacing?: number;
  subset?: string;
  name?: string;
  axes?: Record<string, string>;
  style_name?: string;
  /** Several builds of the font in one: each with its own axis values and style name. */
  styles?: { axes: Record<string, string>; style_name: string }[];
  formats?: Format[];
  static?: boolean;
};

export type Format = "ttf" | "otf" | "woff2";

/** What prepare() planned for one font. */
export type Plan = { paths: string[]; jobs: number; folder: string; entry: ReportEntry };

/** One font's part of the report (report.Entry), handed back to Python as it is. */
export type ReportEntry = Record<string, unknown>;

export type BuildEvent =
  | { type: "log"; font: string; text: string; warning: boolean }
  | {
      type: "job";
      font: string;
      done: number;
      total: number;
      style: string;
      seconds: number;
      /** Its axis values as text, e.g. "wght 375" or "wght 300–700". */
      where: string;
      /** Axis values of a static font. */
      location?: Record<string, number>;
    }
  | { type: "file"; path: string };

export type Files = Record<string, Uint8Array>;

/** An error meant for the user: fontmint's own message, without a Python traceback. */
export class FontmintError extends Error {
  override name = "FontmintError";
}
