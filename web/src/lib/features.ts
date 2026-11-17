// Which features the page offers, how they're labeled and grouped.
import type { FontInfo } from "./types";

/** On by default in browsers and most apps: the page offers to turn these off (--disable). */
const ON_BY_DEFAULT = new Set(["calt", "liga", "clig", "kern", "rlig", "ccmp", "locl", "mark", "mkmk", "curs", "dist"]);

/** Needed to show text correctly in many scripts; offered under "More", since turning them off
 * rarely helps (the core warns about the same ones). */
const SHAPING = new Set([
  "ccmp",
  "locl",
  "mark",
  "mkmk",
  "rlig",
  "curs",
  "dist",
  "rclt",
  "init",
  "medi",
  "fina",
  "isol",
  "abvm",
  "blwm",
  "abvs",
  "blws",
  "akhn",
  "rphf",
  "blwf",
  "half",
  "pstf",
  "vatu",
  "cjct",
  "nukt",
  "rkrf",
  "pref",
  "pres",
  "psts",
  "abvf",
  "ljmo",
  "vjmo",
  "tjmo",
]);

/** Never offered: they only make sense in an app's glyph picker, at a size, or vertically. */
const HIDDEN = new Set(["aalt", "rvrn", "size", "vert", "vrt2", "vkrn", "vpal", "vhal", "valt"]);

const NAMES: Record<string, string> = {
  zero: "Slashed zero",
  tnum: "Tabular figures",
  pnum: "Proportional figures",
  onum: "Oldstyle figures",
  lnum: "Lining figures",
  frac: "Fractions",
  afrc: "Alternative fractions",
  sups: "Superscript",
  subs: "Subscript",
  sinf: "Scientific inferiors",
  numr: "Numerators",
  dnom: "Denominators",
  ordn: "Ordinals",
  case: "Case-sensitive forms",
  salt: "Stylistic alternates",
  dlig: "Discretionary ligatures",
  hlig: "Historical ligatures",
  smcp: "Small capitals",
  c2sc: "Capitals to small capitals",
  pcap: "Petite capitals",
  c2pc: "Capitals to petite capitals",
  unic: "Unicase",
  titl: "Titling",
  swsh: "Swash",
  cswh: "Contextual swash",
  hist: "Historical forms",
  calt: "Contextual alternates",
  liga: "Standard ligatures",
  clig: "Contextual ligatures",
  kern: "Kerning",
  rlig: "Required ligatures",
  ccmp: "Glyph composition",
  locl: "Localized forms",
  mark: "Mark positioning",
  mkmk: "Mark-to-mark positioning",
  curs: "Cursive positioning",
  dist: "Distances",
  cpsp: "Capital spacing",
};

export type Feature = {
  tag: string;
  label: string;
  /** "optional": off by default, can be frozen on. "default": on by default, can be turned off. */
  kind: "optional" | "default";
  /** Rarely changed; shown under "More". */
  shaping: boolean;
};

export function featureLabel(tag: string, fontNames: Record<string, string> = {}): string {
  if (fontNames[tag]) return fontNames[tag];
  if (NAMES[tag]) return NAMES[tag];
  const number = Number(tag.slice(2));
  if (/^ss\d\d$/.test(tag)) return `Stylistic set ${number}`;
  if (/^cv\d\d$/.test(tag)) return `Character variant ${number}`;
  return tag;
}

/** Every feature of the given fonts the page can change, sorted: optional ones (freeze)
 * first, then those on by default (turn off). */
export function featureList(fonts: FontInfo[]): Feature[] {
  const names = Object.assign({}, ...fonts.map((f) => f.feature_names)) as Record<string, string>;
  const substitution = new Set(fonts.flatMap((f) => f.features));
  const positioning = new Set(fonts.flatMap((f) => f.positioning));
  const features: Feature[] = [];
  for (const tag of new Set([...substitution, ...positioning])) {
    if (HIDDEN.has(tag)) continue;
    const kind = ON_BY_DEFAULT.has(tag) || SHAPING.has(tag) ? "default" : "optional";
    // Positioning can't be frozen, and an optional one is already off.
    if (kind === "optional" && !substitution.has(tag)) continue;
    features.push({ tag, label: featureLabel(tag, names), kind, shaping: SHAPING.has(tag) });
  }
  const order = (f: Feature) => `${f.kind === "optional" ? 0 : 1}${f.shaping ? 1 : 0}${f.tag}`;
  return features.toSorted((a, b) => order(a).localeCompare(order(b)));
}

/** OpenType language tags fonts often have their own forms for. */
const LANGUAGES: Record<string, string> = {
  AZE: "Azerbaijani",
  BGR: "Bulgarian",
  BSH: "Bashkir",
  CAT: "Catalan",
  CHU: "Chuvash",
  CRT: "Crimean Tatar",
  DEU: "German",
  ESP: "Spanish",
  FRA: "French",
  GAG: "Gagauz",
  ISM: "Inari Sami",
  KAZ: "Kazakh",
  KSM: "Kildin Sami",
  LSM: "Lule Sami",
  MAH: "Marshallese",
  MKD: "Macedonian",
  MOL: "Moldavian",
  NAV: "Navajo",
  NLD: "Dutch",
  NSM: "Northern Sami",
  PLK: "Polish",
  PTG: "Portuguese",
  ROM: "Romanian",
  SKS: "Skolt Sami",
  SRB: "Serbian",
  SSM: "Southern Sami",
  TAT: "Tatar",
  TRK: "Turkish",
  UKR: "Ukrainian",
  VIT: "Vietnamese",
};

export function languageName(tag: string): string {
  return LANGUAGES[tag] ? `${LANGUAGES[tag]} (${tag})` : tag;
}
