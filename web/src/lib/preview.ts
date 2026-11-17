// CSS for previewing a font: what the build will do, applied live with
// font-feature-settings and font-variation-settings, before anything is built.
import type { Form } from "./options";
import type { FontInfo } from "./types";

/** Tags come from the dropped font, so only well-formed ones reach CSS. */
const TAG = /^[A-Za-z0-9 ]{4}$/;

/** The original font with the form's features: frozen ones on, disabled ones off. */
export function featureSettings(form: Pick<Form, "freeze" | "disable" | "language">): string {
  const freeze = form.language && !form.freeze.includes("locl") ? [...form.freeze, "locl"] : form.freeze;
  const settings = [
    ...freeze.filter((tag) => TAG.test(tag)).map((tag) => `"${tag}" 1`),
    ...form.disable.filter((tag) => TAG.test(tag)).map((tag) => `"${tag}" 0`),
  ];
  return settings.join(", ") || "normal";
}

/** Characters whose glyph the frozen features swap, to mark in the preview. */
export function changedCharacters(info: FontInfo, form: Pick<Form, "freeze">): Set<number> {
  return new Set(form.freeze.flatMap((tag) => info.changes[tag] ?? []));
}

export function variationSettings(location: Record<string, number>): string {
  const settings = Object.entries(location)
    .filter(([tag, value]) => TAG.test(tag) && Number.isFinite(value))
    .map(([tag, value]) => `"${tag}" ${value}`);
  return settings.join(", ") || "normal";
}

/** Line height and letter spacing as CSS, so the original previews like the build will look. */
export function metricsStyle(form: Pick<Form, "lineHeight" | "letterSpacing">): {
  lineHeight?: string;
  letterSpacing?: string;
} {
  const lineHeight = Number(form.lineHeight);
  const letterSpacing = Number(form.letterSpacing);
  return {
    ...(form.lineHeight.trim() && Number.isFinite(lineHeight) ? { lineHeight: String(lineHeight) } : {}),
    ...(form.letterSpacing.trim() && Number.isFinite(letterSpacing) ? { letterSpacing: `${letterSpacing}em` } : {}),
  };
}

let faces = 0;

/** Loads font bytes for use in CSS under a family name of our own (never the font's,
 * which is untrusted). Returns that name, or null if the browser can't use the font. */
export async function loadFace(bytes: Uint8Array): Promise<string | null> {
  const family = `fontmint-preview-${++faces}`;
  try {
    const face = new FontFace(family, bytes.slice().buffer as ArrayBuffer);
    document.fonts.add(await face.load());
    return family;
  } catch {
    return null;
  }
}

export const SAMPLE_TEXT = `0O 1lI| -> => != === <= >= {} [] ()
const greeting = "Hello, world!"; // 2026
The quick brown fox jumps over the lazy dog.
ABCDEFGHIJKLM NOPQRSTUVWXYZ 0123456789`;
