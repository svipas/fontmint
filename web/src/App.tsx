import type { DragEvent } from "react";
import { BuildPanel } from "./components/BuildPanel";
import { DropZone } from "./components/DropZone";
import { FontList } from "./components/FontList";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { Options } from "./components/Options";
import { Preview } from "./components/Preview";
import { useStore } from "./store";

export function App() {
  const hasFonts = useStore((s) => s.fonts.length > 0);
  const addFiles = useStore((s) => s.addFiles);

  // Fonts can be dropped anywhere once the workspace is open; elsewhere the browser
  // would open the file instead.
  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    if (event.dataTransfer.files.length) addFiles([...event.dataTransfer.files]);
  };

  return (
    <div className="flex min-h-dvh flex-col" onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
      <Header />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 pt-6 sm:px-6 sm:pt-10">
        {hasFonts ? (
          // auto 1fr: a taller preview grows the second row, not the font list's.
          <div className="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(320px,380px)] lg:grid-rows-[auto_1fr]">
            <div className="lg:col-start-2 lg:row-start-1">
              <FontList />
            </div>
            {/* Spans both rows on wide screens, so the preview can stay pinned while the options scroll. */}
            <div className="lg:col-start-1 lg:row-span-2 lg:row-start-1">
              <div className="lg:sticky lg:top-4">
                <Preview />
              </div>
            </div>
            <div className="lg:col-start-2 lg:row-start-2">
              <Options />
            </div>
            <BuildPanel />
          </div>
        ) : (
          <DropZone />
        )}
      </main>
      <Footer />
    </div>
  );
}
