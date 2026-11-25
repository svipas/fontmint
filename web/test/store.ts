import { store, type FontEntry, type State } from "../src/store";
import { emptyForm } from "../src/lib/options";
import type { FontInfo } from "../src/lib/types";
import { fontInfo } from "./fonts";

const initial = store.state;

export function resetStore(): void {
  store.setState(() => initial);
}

export function setState(change: Partial<State>): void {
  store.setState((state) => ({ ...state, ...change }));
}

export function withFonts(...infos: Partial<FontInfo>[]): void {
  const fonts: FontEntry[] = infos.map((change, i) => ({
    name: `Font${i}.ttf`,
    bytes: new Uint8Array(),
    info: fontInfo(change),
    error: null,
    face: null,
  }));
  setState({ fonts, form: { ...emptyForm } });
}
