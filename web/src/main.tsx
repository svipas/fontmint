import { StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { App } from "./App";
import { store } from "./store";

const app = (
  <StrictMode>
    <App />
  </StrictMode>
);

// In development the root survives hot reloads, so the page keeps its fonts and options.
if (import.meta.hot) {
  const root: Root = (import.meta.hot.data.root ??= createRoot(document.getElementById("root")!));
  root.render(app);
} else {
  createRoot(document.getElementById("root")!).render(app);
}

// On phones, and in browsers told to save data, Python starts with "Choose fonts" instead.
const { connection } = navigator as Navigator & { connection?: { saveData?: boolean } };
if (!connection?.saveData && !matchMedia("(pointer: coarse)").matches) store.actions.warmUp();
