import { useSelector } from "@tanstack/react-store";
import { TriangleAlertIcon, XIcon } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardAction, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { familyOf, type FontEntry, store } from "@/store";
import { AddFontsButton, ReadyStatus } from "./DropZone";
import { CARD } from "./ui";

function summary(font: FontEntry): string {
  const info = font.info!;
  const kind = info.variable ? (info.cff2 ? "Variable OTF (CFF2)" : "Variable") : "Static";
  const parts = [info.italic ? `${kind} italic` : kind];
  if (info.variable) {
    parts.push(`${info.axes.length} ${info.axes.length === 1 ? "axis" : "axes"}`);
    parts.push(`${info.instances.length} styles`);
  }
  parts.push(`${info.features.length + info.positioning.length} features`);
  return parts.filter(Boolean).join(" · ");
}

export function FontList() {
  const fonts = useSelector(store, (s) => s.fonts);
  const notice = useSelector(store, (s) => s.notice);
  const running = useSelector(store, (s) => s.build.status === "running");
  const families = [...new Set(fonts.flatMap((f) => (f.info ? [familyOf(f.info)] : [])))];

  return (
    <Card className={CARD}>
      <CardHeader className="items-center">
        <CardTitle className="text-sm font-semibold">
          <h2>Your fonts</h2>
        </CardTitle>
        <CardAction className="self-center">
          <AddFontsButton />
        </CardAction>
      </CardHeader>
      <CardContent className="space-y-4">
        <ul className="space-y-2">
          {fonts.map((font) => (
            <li key={font.name} className="flex items-start justify-between gap-3 rounded-xl bg-muted px-3 py-2.5">
              <div className="min-w-0 flex-1 space-y-0.5">
                {/* While a font is read, placeholders hold the lines its details will fill, so
                    the row doesn't grow when they arrive. */}
                {font.info ? (
                  <p className="truncate text-sm font-medium motion-safe:animate-in motion-safe:fade-in">
                    {font.info.family}
                  </p>
                ) : (
                  !font.error && (
                    <div className="flex h-5 items-center">
                      <Skeleton className="h-4 w-28 bg-secondary" />
                    </div>
                  )
                )}
                <p className="truncate font-mono text-xs text-muted-foreground" title={font.name}>
                  {font.name}
                </p>
                {font.info && (
                  <p className="text-xs text-muted-foreground motion-safe:animate-in motion-safe:fade-in">
                    {summary(font)}
                  </p>
                )}
                {font.info?.variable && (
                  <p className="text-xs text-muted-foreground motion-safe:animate-in motion-safe:fade-in">
                    {font.info.axes.map(([tag, min, , max]) => `${tag} ${min}–${max}`).join(", ")}
                  </p>
                )}
                {!font.info && !font.error && (
                  <>
                    <p className="text-xs text-muted-foreground">Reading font…</p>
                    <div className="flex h-4 items-center">
                      <Skeleton className="h-3 w-36 bg-secondary" />
                    </div>
                  </>
                )}
                {font.error && (
                  <p role="alert" className="text-xs text-destructive">
                    {font.error}
                  </p>
                )}
                {font.info && !font.face && (
                  <p className="text-xs text-muted-foreground">
                    Your browser can&apos;t display this font, so there&apos;s no preview.
                  </p>
                )}
              </div>
              <Button
                variant="ghost"
                size="icon-xs"
                disabled={running}
                onClick={() => store.actions.removeFont(font.name)}
                aria-label={`Remove ${font.name}`}
              >
                <XIcon />
              </Button>
            </li>
          ))}
        </ul>
        {families.length > 1 && (
          <Alert className="border-warning/40 bg-warning/5">
            <TriangleAlertIcon className="text-warning" />
            <AlertTitle>Fonts from {families.length} families</AlertTitle>
            <AlertDescription className="text-foreground/80">
              One build makes one family: {new Intl.ListFormat("en").format(families)} would all get the same name and
              options, and same-named styles can&apos;t both be built. Build each family on its own.
            </AlertDescription>
          </Alert>
        )}
        <div aria-live="polite" className="empty:mb-0">
          {notice && <p className="text-xs wrap-anywhere text-muted-foreground">{notice}</p>}
        </div>
        <ReadyStatus />
      </CardContent>
    </Card>
  );
}
