import {
  ArrowDownIcon,
  CheckIcon,
  ChevronRightIcon,
  CopyIcon,
  DownloadIcon,
  TriangleAlertIcon,
  XCircleIcon,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Progress } from "@/components/ui/progress";
import { cliCommands, formErrors } from "@/lib/options";
import { cn } from "@/lib/utils";
import { type BuildState, type FontEntry, useStore } from "@/store";
import { CARD, duration, fileSize, INSTALL, REPO } from "./ui";

const STAGES = {
  starting: "Getting fontmint ready…",
  preparing: "Freezing features and renaming…",
  building: "Building fonts…",
  zipping: "Zipping…",
};

export function BuildPanel() {
  const fonts = useStore((s) => s.fonts);
  const form = useStore((s) => s.form);
  const build = useStore((s) => s.build);
  const startBuild = useStore((s) => s.startBuild);
  const cancelBuild = useStore((s) => s.cancelBuild);
  const log = useStore((s) => s.log);
  const warnings = useStore((s) => s.warnings.length);
  const infos = fonts.flatMap((f) => (f.info ? [f.info] : []));
  const errors = formErrors(form, infos);
  const problems = Object.keys(errors).length;
  // What stops the build, and the field that fixes it (a selector), if there is one.
  const [blocked, field] = fonts.some((f) => f.error)
    ? ["Remove the file that couldn't be read to build.", null]
    : !fonts.every((f) => f.info)
      ? ["Reading your fonts…", null]
      : !form.name.trim()
        ? ["Give your build a family name to start.", "#name"]
        : problems
          ? [
              `Fix the ${problems === 1 ? "marked field" : `${problems} marked fields`} to build.`,
              "[aria-invalid=true]",
            ]
          : [null, null];

  return (
    <>
      {/* Pinned to the bottom of the window, so Build is in reach wherever the options are scrolled to. */}
      <Card size="sm" className="sticky bottom-3 z-10 shadow-lg lg:col-span-2">
        <CardContent className="space-y-3">
          <div className="flex flex-wrap items-center gap-3">
            {build.status === "running" ? (
              <Button variant="outline" size="lg" onClick={cancelBuild}>
                Cancel
              </Button>
            ) : (
              <Button size="lg" className="px-5" disabled={Boolean(blocked)} onClick={startBuild}>
                {build.status === "done" ? "Build again" : "Build fonts"}
              </Button>
            )}
            {build.status === "done" && (
              <a
                href={build.url}
                download={build.fileName}
                className={cn(buttonVariants({ variant: "secondary", size: "lg" }), "max-w-full")}
              >
                <DownloadIcon />
                <span className="truncate">Download {build.fileName}</span>{" "}
                <span className="shrink-0">· {fileSize(build.size)}</span>
              </a>
            )}
            {build.status !== "running" &&
              blocked &&
              (field ? (
                // Easy to miss in the options: this takes the user to the field.
                <Button
                  variant="link"
                  className="h-auto px-0 text-sm font-normal text-muted-foreground underline decoration-muted-foreground/50 underline-offset-3 hover:text-foreground hover:decoration-foreground/60"
                  onClick={() => reveal(field, field, "center")}
                >
                  {blocked}
                </Button>
              ) : (
                <p className="text-sm text-muted-foreground">{blocked}</p>
              ))}
            {/* The log, warnings and command line are below the pinned bar, easy to miss. */}
            {log.length > 0 && (
              <Button variant="ghost" className="ml-auto" onClick={() => reveal("#build-details", "#build-log")}>
                {warnings ? `${warnings} ${warnings === 1 ? "warning" : "warnings"}` : "Build log"}
                <ArrowDownIcon />
              </Button>
            )}
          </div>
          <Status build={build} />
        </CardContent>
      </Card>
      {(fonts.some((f) => f.info) || log.length > 0) && (
        <Card id="build-details" className={cn(CARD, "lg:col-span-2 motion-safe:animate-in motion-safe:fade-in")}>
          <CardContent className="space-y-4">
            <Warnings />
            <Log />
            <CliCommand fonts={fonts} />
          </CardContent>
        </Card>
      )}
    </>
  );
}

/** Scrolls the first element matching `target` into view and moves the focus to `focus`. */
function reveal(target: string, focus: string, block: ScrollLogicalPosition = "start") {
  const element = document.querySelector<HTMLElement>(target);
  if (!element) return;
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  element.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block });
  document.querySelector<HTMLElement>(focus)?.focus({ preventScroll: true });
}

function Status({ build }: { build: BuildState }) {
  const preview = useStore((s) => s.built.length > 0);
  if (build.status === "running") {
    const fraction = build.stage === "building" && build.total ? build.done / build.total : null;
    return (
      <div className="space-y-2" aria-live="polite">
        <div className="flex justify-between gap-3 text-sm">
          <span>{STAGES[build.stage]}</span>
          {build.stage === "building" && (
            <span className="text-muted-foreground tabular-nums">
              {build.done} of {build.total} fonts
              {build.left !== null &&
                build.done > 0 &&
                build.done < build.total &&
                ` · about ${duration(build.left)} left`}
            </span>
          )}
        </div>
        <Progress
          aria-label="Build progress"
          value={fraction === null ? null : Math.round(fraction * 100)}
          className={fraction === null ? "animate-pulse" : undefined}
        />
      </div>
    );
  }
  if (build.status === "done") {
    return (
      <p className="flex items-center gap-1.5 text-sm text-muted-foreground" aria-live="polite">
        <CheckIcon className="size-4 text-primary" aria-hidden="true" />
        Built {build.files} {build.files === 1 ? "font file" : "font files"} in {duration(build.seconds)}.
        {preview && " The preview now shows your build."}
      </p>
    );
  }
  if (build.status === "failed") {
    return (
      <Alert variant="destructive">
        <XCircleIcon />
        <AlertTitle>The build failed</AlertTitle>
        <AlertDescription className="text-destructive/90">
          <p className="break-words">{build.error}</p>
          {!build.user && (
            <p className="mt-2 text-xs">
              This looks like a bug in fontmint. <a href={`${REPO}/issues`}>Please report it</a> with the log below.
            </p>
          )}
        </AlertDescription>
      </Alert>
    );
  }
  return null;
}

function Warnings() {
  const warnings = useStore((s) => s.warnings);
  if (!warnings.length) return null;
  return (
    <Alert className="border-warning/40 bg-warning/5">
      <TriangleAlertIcon className="text-warning" />
      <AlertTitle>{warnings.length === 1 ? "Warning" : `${warnings.length} warnings`}</AlertTitle>
      <AlertDescription className="text-foreground/80">
        <ul className="list-disc space-y-1 pl-4">
          {warnings.map((warning) => (
            <li key={warning}>{warning}</li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

function useCopy(): [boolean, (text: string) => Promise<void>] {
  const [copied, setCopied] = useState(false);
  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      return; // the browser refused (no permission): the text is still there to select
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return [copied, copy];
}

function Log() {
  const log = useStore((s) => s.log);
  const box = useRef<HTMLPreElement>(null);
  const following = useRef(true);
  const [copied, copy] = useCopy();

  // Follows new lines, unless the user scrolled up to read.
  useEffect(() => {
    const element = box.current;
    if (element && following.current && log.length) element.scrollTop = element.scrollHeight;
  }, [log.length]);

  if (!log.length) return null;
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <p className="eyebrow">Build log</p>
        <Button variant="ghost" size="xs" onClick={() => copy(log.map((line) => line.text).join("\n"))}>
          {copied ? <CheckIcon /> : <CopyIcon />}
          {copied ? "Copied" : "Copy log"}
        </Button>
      </div>
      <pre
        ref={box}
        id="build-log"
        // Focusable, so keyboard users can scroll it.
        // oxlint-disable-next-line jsx-a11y/no-noninteractive-tabindex
        tabIndex={0}
        aria-label="Build log"
        onScroll={(event) => {
          const element = event.currentTarget;
          following.current = element.scrollHeight - element.scrollTop - element.clientHeight < 24;
        }}
        className="max-h-60 overflow-auto rounded-xl border bg-crust p-3 font-mono text-xs leading-relaxed text-subtext"
      >
        {log.map((line, i) => (
          // oxlint-disable-next-line react/no-array-index-key -- lines are only ever appended
          <div key={i} className={line.warning ? "text-warning" : undefined}>
            {line.text}
          </div>
        ))}
      </pre>
    </div>
  );
}

function CliCommand({ fonts }: { fonts: FontEntry[] }) {
  const form = useStore((s) => s.form);
  const [copied, copy] = useCopy();
  const read = fonts.filter((f) => f.info);
  if (!read.length) return null;
  const commands = cliCommands(
    read.map((f) => f.name),
    form,
    read.map((f) => f.info!),
  );
  const command = commands.join("\n");
  return (
    <Collapsible className="rounded-xl border">
      <CollapsibleTrigger className="group flex w-full cursor-pointer items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
        <ChevronRightIcon className="size-4 text-muted-foreground transition-transform group-data-panel-open:rotate-90" />
        The same build on the command line
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-2 border-t p-3">
        <p className="text-xs text-muted-foreground">
          The{" "}
          <a href={INSTALL} className="underline underline-offset-3 hover:text-foreground">
            fontmint command line
          </a>{" "}
          also makes hinted fonts and static OTF; there it builds every format unless you pick some.
          {commands.length > 1 && " Your fonts don't all take the same options, so there is one command for each."}
        </p>
        <div className="flex items-start gap-2">
          <code className="block min-w-0 flex-1 overflow-x-auto rounded-lg border bg-crust p-2.5 font-mono text-xs whitespace-pre text-subtext">
            {command}
          </code>
          <Button variant="outline" size="sm" onClick={() => copy(command)}>
            {copied ? <CheckIcon /> : <CopyIcon />}
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
