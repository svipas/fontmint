// Small pieces shared by the page's sections.
import { ChevronRightIcon, RotateCcwIcon, TerminalIcon } from "lucide-react";
import { type ReactNode, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

export const REPO = "https://github.com/svipas/fontmint";
export const WEB_LIMITS = `${REPO}#web-version`;
export const INSTALL = `${REPO}#installation`;

export function megabytes(bytes: number): string {
  return `${(bytes / 2 ** 20).toFixed(1)} MB`;
}

/** A file's size: kilobytes below 1 MB, so a small zip doesn't read "0.0 MB". */
export function fileSize(bytes: number): string {
  return bytes < 2 ** 20 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : megabytes(bytes);
}

export function duration(seconds: number): string {
  if (seconds < 60) return `${Math.max(1, Math.round(seconds))} s`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

/** The page's cards: shadcn's Card with roomier spacing from tablet width up. */
export const CARD = "sm:[--card-spacing:--spacing(5)]";

/** A label with the CLI flag it maps to: fontmint's messages name flags. */
export function FlagLabel({ text, flag }: { text: ReactNode; flag?: string }) {
  return (
    <span className="flex w-full items-baseline justify-between gap-2">
      <span>{text}</span>
      {flag && <span className="flag">{flag}</span>}
    </span>
  );
}

export function ResetButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <Button
      variant="ghost"
      size="xs"
      className="relative text-muted-foreground after:absolute after:-inset-x-1 after:-inset-y-2"
      aria-label={label}
      title={label}
      onClick={onClick}
    >
      <RotateCcwIcon />
      <span className="max-[340px]:hidden">Reset</span>
    </Button>
  );
}

/** A section of the options. Advanced ones start closed, and open by themselves when
 * something in them is set, so nothing changes the build out of sight. */
export function Section({
  title,
  summary,
  defaultOpen = true,
  onReset,
  children,
}: {
  title: string;
  /** What is set inside, in a few words, shown while the section is closed. */
  summary?: string;
  defaultOpen?: boolean;
  /** Given while something in the section is changed: puts it back to the defaults. */
  onReset?: () => void;
  children: ReactNode;
}) {
  // Decided once: the section shouldn't close while the user works in it.
  const [initiallyOpen] = useState(defaultOpen || Boolean(summary));
  const trigger = useRef<HTMLButtonElement>(null);
  return (
    <Collapsible defaultOpen={initiallyOpen} className="border-t pt-4 first:border-t-0 first:pt-0">
      <div className="flex items-center gap-2">
        <CollapsibleTrigger
          ref={trigger}
          className="group flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-md py-1 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground transition-transform group-data-panel-open:rotate-90" />
          <span className="eyebrow">{title}</span>
          {summary && (
            <Badge
              variant="secondary"
              className="ml-auto max-w-[60%] truncate font-normal group-data-panel-open:hidden"
            >
              {summary}
            </Badge>
          )}
        </CollapsibleTrigger>
        {onReset && (
          <ResetButton
            label={`Reset ${title.toLowerCase()}`}
            onClick={() => {
              onReset();
              trigger.current?.focus();
            }}
          />
        )}
      </div>
      <CollapsibleContent className="space-y-4 pt-3">{children}</CollapsibleContent>
    </Collapsible>
  );
}

/** What the browser can't build, and the way to the command line that can. */
export function CliNote({ className }: { className?: string }) {
  return (
    <div className={cn("flex gap-3 rounded-xl border border-dashed p-3", className)}>
      <TerminalIcon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
      <div className="space-y-2.5">
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">Need hinted fonts or static OTF?</span> The browser builds
          unhinted TTF and WOFF2. Hinting (ttfautohint) and OTF outlines need the fontmint command line.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <a href={INSTALL} className={buttonVariants({ variant: "outline", size: "sm" })}>
            Install the CLI
          </a>
          <a href={WEB_LIMITS} className="text-xs underline underline-offset-3 hover:text-foreground">
            What the web version can&apos;t do
          </a>
        </div>
      </div>
    </div>
  );
}

export function GitHubIcon({ className = "size-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true" className={className} fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}
