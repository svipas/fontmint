import { type CSSProperties, useEffect, useRef, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { changedCharacters, featureSettings, metricsStyle, SAMPLE_TEXT, variationSettings } from "@/lib/preview";
import { cn } from "@/lib/utils";
import { defaultAxes, type PreviewMode, useStore } from "@/store";
import { CARD, ResetButton } from "./ui";

const HIGHLIGHT = "fontmint-changed";
const SIZE = 28;

export function Preview() {
  const allFonts = useStore((s) => s.fonts);
  const fonts = allFonts.filter((f) => f.info && f.face);
  const form = useStore((s) => s.form);
  const sample = useStore((s) => s.sample) || SAMPLE_TEXT;
  const setSample = useStore((s) => s.setSample);
  const previewAxes = useStore((s) => s.previewAxes);
  const setPreviewAxis = useStore((s) => s.setPreviewAxis);
  const resetPreviewAxes = useStore((s) => s.resetPreviewAxes);
  const builtFonts = useStore((s) => s.built);
  const builtWith = useStore((s) => s.builtWith);
  const mode = useStore((s) => s.previewMode);
  const setMode = useStore((s) => s.setPreviewMode);
  const [selected, setSelected] = useState(0);
  const [size, setSize] = useState(SIZE);
  const [marking, setMarking] = useState(true);
  const copy = useRef<HTMLDivElement>(null);
  const original = useRef<HTMLDivElement>(null);
  const toolbar = useRef<HTMLDivElement>(null);

  const font = fonts[Math.min(selected, fonts.length - 1)];
  const built = mode === "build" ? builtFonts.find((b) => b.font === font?.name) : undefined;
  const changed = font?.info && marking ? changedCharacters(font.info, built ? builtWith! : form) : null;

  // Marks the changed characters without touching the text, so shaping stays exactly as
  // without marks (the CSS Custom Highlight API; browsers without it show no marks).
  useEffect(() => {
    if (typeof CSS === "undefined" || !("highlights" in CSS)) return;
    const ranges: Range[] = [];
    for (const element of [copy.current, original.current]) {
      const node = element?.firstChild;
      if (!changed?.size || node?.nodeType !== Node.TEXT_NODE) continue;
      let offset = 0;
      for (const char of sample) {
        if (changed.has(char.codePointAt(0)!)) {
          const range = new Range();
          range.setStart(node, offset);
          range.setEnd(node, offset + char.length);
          ranges.push(range);
        }
        offset += char.length;
      }
    }
    CSS.highlights.set(HIGHLIGHT, new Highlight(...ranges));
    return () => void CSS.highlights.delete(HIGHLIGHT);
  }, [changed, sample, copy, original]);

  if (!font?.info || !font.face) {
    return (
      <Card className={cn(CARD, "min-h-64 justify-center")}>
        <CardContent className="text-center text-muted-foreground">
          The preview appears once a font is read.
        </CardContent>
      </Card>
    );
  }

  const staticBuild = built && Object.keys(built.location).length > 0;
  const location = staticBuild
    ? built.location
    : Object.fromEntries(font.info.axes.map(([tag]) => [tag, previewAxes[tag] ?? 0]));
  const defaults = defaultAxes(allFonts);
  const moved = size !== SIZE || (!staticBuild && Object.entries(defaults).some(([tag, v]) => previewAxes[tag] !== v));
  const base: CSSProperties = {
    fontFamily: `"${font.face}", var(--font-mono)`,
    fontSize: `${size}px`,
    fontVariationSettings: variationSettings(location),
  };
  const yours: CSSProperties = built
    ? {
        ...base,
        fontFamily: `"${built.face}", var(--font-mono)`,
        fontVariationSettings: staticBuild ? "normal" : base.fontVariationSettings,
      }
    : { ...base, fontFeatureSettings: featureSettings(form), ...metricsStyle(form) };
  // "Upright" and "Italic" while that tells the fonts apart; otherwise their file names.
  const styles = fonts.map((f) => (f.info?.italic ? "Italic" : "Upright"));
  const distinct = new Set(styles).size === fonts.length;
  const labels = Object.fromEntries(fonts.map((f, i) => [f.name, distinct ? styles[i] : f.name]));
  const text = "w-full resize-none bg-transparent whitespace-pre-wrap break-words outline-none leading-snug";
  const where = Object.entries(built?.location ?? {})
    .map(([tag, value]) => `${tag} ${value}`)
    .join(", ");

  return (
    <Card className={cn(CARD, "gap-0 py-0 motion-safe:animate-in motion-safe:fade-in")}>
      <div ref={toolbar} className="space-y-3 border-b px-4 py-3">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
          {builtFonts.length > 0 && (
            <ToggleGroup
              aria-label="What the preview shows"
              variant="outline"
              size="sm"
              spacing={0}
              value={[mode]}
              onValueChange={(value: string[]) => value[0] && setMode(value[0] as PreviewMode)}
            >
              <ToggleGroupItem value="live">Live preview</ToggleGroupItem>
              <ToggleGroupItem value="build">Your build</ToggleGroupItem>
            </ToggleGroup>
          )}
          {fonts.length > 1 && (
            <ToggleGroup
              aria-label="Font to preview"
              size="sm"
              className="max-w-full flex-wrap"
              value={[font.name]}
              onValueChange={(value: string[]) => {
                const index = fonts.findIndex((f) => f.name === value[0]);
                if (index >= 0) setSelected(index);
              }}
            >
              {fonts.map((f) => (
                <ToggleGroupItem key={f.name} value={f.name} title={f.name}>
                  {labels[f.name]}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
          )}
          <AxisSlider label="Size" value={size} min={12} max={96} step={1} unit="px" onChange={setSize} />
          {!staticBuild &&
            font.info.axes.map(([tag, min, , max]) => (
              <AxisSlider
                key={tag}
                label={tag}
                value={location[tag]!}
                min={min}
                max={max}
                step={tag === "wght" || tag === "wdth" ? 1 : 0.1}
                onChange={(value) => setPreviewAxis(tag, value)}
              />
            ))}
        </div>
        <div className="flex items-center justify-between gap-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2">
            <Switch id="mark-changes" size="sm" checked={marking} onCheckedChange={setMarking} />
            <label htmlFor="mark-changes" className="flex cursor-pointer items-center gap-1.5">
              <span
                className="inline-block size-2.5 rounded-sm border-b-2 border-yellow bg-yellow/25"
                aria-hidden="true"
              />
              Mark changed characters
            </label>
          </div>
          {moved && (
            <div className="-my-1">
              <ResetButton
                label="Reset size and axes"
                onClick={() => {
                  setSize(SIZE);
                  resetPreviewAxes();
                  toolbar.current?.querySelector<HTMLElement>('input[type="range"]')?.focus();
                }}
              />
            </div>
          )}
        </div>
      </div>

      <div className="space-y-1.5 p-4 sm:p-6">
        <p className="eyebrow flex flex-wrap gap-x-2 text-primary">
          {built ? (
            <>
              Your build
              <span className="font-mono font-normal tracking-normal normal-case">
                {built.path.split("/").pop()}
                {where && ` · ${where}`}
              </span>
            </>
          ) : (
            <>
              With your changes
              <span className="font-normal tracking-normal text-muted-foreground normal-case">
                · type to try your own text
              </span>
            </>
          )}
        </p>
        {built && builtWith !== form && (
          <p className="text-xs text-warning">You changed options after this build. Build again to see them here.</p>
        )}
        {/* The copy behind the text box sizes it to its text and carries the marks. */}
        <div className="grid grid-cols-[minmax(0,1fr)]">
          <div
            ref={copy}
            aria-hidden="true"
            className={`${text} col-start-1 row-start-1 text-transparent`}
            style={yours}
          >
            {`${sample}\n`}
          </div>
          <textarea
            aria-label={built ? "Preview text in your build" : "Preview text with your changes"}
            value={sample}
            rows={1}
            spellCheck={false}
            onChange={(event) => setSample(event.target.value)}
            className={`${text} relative col-start-1 row-start-1 overflow-hidden`}
            style={yours}
          />
        </div>
      </div>
      <div className="space-y-1.5 border-t border-dashed bg-muted/60 p-4 sm:p-6">
        <p className="eyebrow">Original</p>
        <div ref={original} className={`${text} text-muted-foreground`} style={base}>
          {sample}
        </div>
      </div>
    </Card>
  );
}

function AxisSlider(props: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit?: string;
  onChange: (value: number) => void;
}) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="font-mono text-muted-foreground" aria-hidden="true">
        {props.label}
      </span>
      <Slider
        className="w-24"
        thumbLabel={props.label}
        value={[props.value]}
        min={props.min}
        max={props.max}
        step={props.step}
        onValueChange={(value) => props.onChange(Array.isArray(value) ? value[0]! : value)}
      />
      <span className="min-w-10 font-mono tabular-nums">
        {Number(props.value.toFixed(1))}
        {props.unit}
      </span>
    </div>
  );
}
