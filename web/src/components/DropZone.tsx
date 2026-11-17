import { LockIcon, PlusIcon, TerminalIcon, UploadIcon } from "lucide-react";
import { type DragEvent, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";
import { useStore } from "@/store";
import { INSTALL, megabytes, WEB_LIMITS } from "./ui";

const ACCEPT = ".ttf,.otf,.woff2";

function FileInput({ onFiles }: { onFiles: (files: File[]) => void }) {
  return (
    <input
      type="file"
      accept={ACCEPT}
      multiple
      hidden
      onChange={(event) => {
        onFiles([...(event.target.files ?? [])]);
        event.target.value = "";
      }}
    />
  );
}

/** The big drop area shown before any font is added. */
export function DropZone() {
  const addFiles = useStore((s) => s.addFiles);
  const input = useRef<HTMLDivElement>(null);
  const [over, setOver] = useState(false);

  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-8 text-center sm:mb-10">
        <h1 className="text-4xl font-bold tracking-tight text-balance sm:text-5xl">Make a font yours.</h1>
        <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-pretty text-muted-foreground sm:text-lg">
          Make stylistic sets and other features the default, rename the family, adjust spacing, and export variable and
          static fonts - without a font editor.
        </p>
      </div>
      {/* A drop target; the button inside is its keyboard and screen reader way in. */}
      {/* oxlint-disable-next-line jsx-a11y/no-noninteractive-element-interactions */}
      <section
        aria-label="Add fonts"
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={(event: DragEvent) => {
          // Not when the pointer only moves onto something inside the drop area.
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(false);
        }}
        // The drop itself bubbles up to the page, which adds the files (App.tsx).
        onDrop={() => setOver(false)}
        className={cn(
          "flex flex-col items-center gap-4 rounded-3xl border-2 border-dashed bg-card px-6 py-14 text-center transition-colors sm:py-20",
          over ? "border-primary bg-primary/5" : "border-input",
        )}
      >
        <UploadIcon className="size-8 text-primary" aria-hidden="true" />
        <p className="text-lg font-semibold">Drop font files here</p>
        <div ref={input}>
          <Button size="lg" className="px-5" onClick={() => input.current?.querySelector("input")?.click()}>
            Choose fonts
          </Button>
          <FileInput onFiles={addFiles} />
        </div>
        <p className="max-w-sm text-xs leading-relaxed text-muted-foreground">
          TTF, OTF or WOFF2, variable or static. Add an upright and its italic together to build the whole family.
        </p>
      </section>
      <div className="mt-5 flex flex-col items-center gap-2 text-center text-sm text-muted-foreground">
        <p className="flex items-center gap-1.5 font-medium text-foreground">
          <LockIcon className="size-3.5 text-primary" aria-hidden="true" />
          Your fonts never leave your computer: fontmint runs right here, in your browser.
        </p>
        <p className="text-xs">
          Check that your font&apos;s license allows modification. Most open fonts (SIL OFL) do.
        </p>
        <p className="flex flex-wrap items-center justify-center gap-1.5 text-xs">
          <TerminalIcon className="size-3.5" aria-hidden="true" />
          Hinted fonts and static OTF need the command line:{" "}
          <a href={INSTALL} className="font-medium text-primary underline underline-offset-3">
            Install the CLI
          </a>{" "}
          ·{" "}
          <a href={WEB_LIMITS} className="underline underline-offset-3 hover:text-foreground">
            What the web version can&apos;t do
          </a>
        </p>
      </div>
    </div>
  );
}

/** A smaller "add more" button, once fonts are in. */
export function AddFontsButton() {
  const addFiles = useStore((s) => s.addFiles);
  const running = useStore((s) => s.build.status === "running");
  const input = useRef<HTMLDivElement>(null);
  return (
    <div ref={input}>
      <Button
        variant="outline"
        size="sm"
        disabled={running}
        onClick={() => input.current?.querySelector("input")?.click()}
      >
        <PlusIcon />
        Add fonts
      </Button>
      <FileInput onFiles={addFiles} />
    </div>
  );
}

/** Getting Pyodide and fontmint ready: a download, then starting Python. */
export function ReadyStatus() {
  const download = useStore((s) => s.download);
  const manifest = useStore((s) => s.manifest);
  const fonts = useStore((s) => s.fonts);
  // One block from the first download to the last font read, the same height throughout,
  // so the page around it doesn't move until everything appears at once.
  if (!download || fonts.every((f) => f.info || f.error)) return null;
  const downloading = !manifest && download.total > 0 && download.loaded < download.total;
  const [label, hint] = manifest
    ? ["Reading your fonts…", "Finding their axes, styles and features."]
    : downloading
      ? [
          `Getting fontmint ready · ${megabytes(download.loaded)} of ${megabytes(download.total)}`,
          "Only on your first visit; your browser keeps it for next time.",
        ]
      : ["Starting Python…", "fontmint runs right here, in your browser."];
  return (
    <div className="space-y-2" aria-live="polite">
      <p className="text-sm text-muted-foreground">{label}</p>
      <Progress
        aria-label="Getting fontmint ready"
        value={!manifest && download.total ? Math.round((download.loaded / download.total) * 100) : null}
      />
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}
