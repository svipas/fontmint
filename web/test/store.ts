// Puts the page's store into a known state for a component test.
import { useStore, type FontEntry } from "../src/store";
import { emptyForm } from "../src/lib/options";
import type { FontInfo } from "../src/lib/types";
import { fontInfo } from "./fonts";

const initial = useStore.getState();

export function resetStore(): void {
  useStore.setState(initial, true);
}

export function withFonts(...infos: Partial<FontInfo>[]): void {
  const fonts: FontEntry[] = infos.map((change, i) => ({
    name: `Font${i}.ttf`,
    bytes: new Uint8Array(),
    info: fontInfo(change),
    error: null,
    face: null,
  }));
  useStore.setState({ fonts, form: { ...emptyForm } });
}
