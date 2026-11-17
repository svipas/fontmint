import { ArrowRightIcon, ChevronRightIcon, PlusIcon, SearchIcon, XIcon } from "lucide-react";
import { type ReactNode, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from "@/components/ui/input-group";
import {
  Popover,
  PopoverContent,
  PopoverDescription,
  PopoverHeader,
  PopoverTitle,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { type Feature, featureList, languageName } from "@/lib/features";
import { axisRanges, emptyStyle, type FormErrors, formErrors, type Style, SUBSETS } from "@/lib/options";
import { featureSettings, variationSettings } from "@/lib/preview";
import type { FontInfo } from "@/lib/types";
import { cn } from "@/lib/utils";
import { type FontEntry, useStore } from "@/store";
import { CARD, CliNote, FlagLabel, Section } from "./ui";

const AXIS_NAMES: Record<string, [label: string, flag: string]> = {
  wght: ["Weight", "--weight"],
  wdth: ["Width", "--width"],
  slnt: ["Slant", "--slant"],
  ital: ["Italic", "--italic"],
  opsz: ["Optical size", "--optical-size"],
};

type ReadFont = FontEntry & { info: FontInfo };

export function Options() {
  const fonts = useStore((s) => s.fonts).filter((f): f is ReadFont => f.info !== null);
  const infos = fonts.map((f) => f.info);
  const form = useStore((s) => s.form);
  if (!infos.length) return null;
  const errors = formErrors(form, infos);
  return (
    <Card className={cn(CARD, "motion-safe:animate-in motion-safe:fade-in")}>
      <CardContent className="space-y-4">
        <NameField family={infos[0]!.family} error={errors.name} />
        <Features fonts={fonts} />
        <Spacing infos={infos} errors={errors} />
        <Characters errors={errors} />
        {infos.some((info) => info.variable) && <Output infos={infos} errors={errors} />}
      </CardContent>
    </Card>
  );
}

function TextField(props: {
  id: string;
  label: string;
  flag?: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  description?: ReactNode;
  error?: string;
  className?: string;
  inputMode?: "decimal" | "text";
  onBlur?: () => void;
}) {
  return (
    <Field data-invalid={Boolean(props.error)} className="gap-1.5">
      <FieldLabel htmlFor={props.id} className="w-full">
        <FlagLabel text={props.label} flag={props.flag} />
      </FieldLabel>
      <Input
        id={props.id}
        className={props.className}
        value={props.value}
        inputMode={props.inputMode}
        placeholder={props.placeholder}
        aria-invalid={Boolean(props.error)}
        onChange={(event) => props.onChange(event.target.value)}
        onBlur={props.onBlur}
      />
      {props.error ? (
        <FieldError className="text-xs">{props.error}</FieldError>
      ) : (
        props.description && <FieldDescription className="text-xs">{props.description}</FieldDescription>
      )}
    </Field>
  );
}

function NameField({ family, error }: { family: string; error?: string }) {
  const name = useStore((s) => s.form.name);
  const setForm = useStore((s) => s.setForm);
  // "Required" waits until the field was left once; other problems show as you type.
  const [left, setLeft] = useState(false);
  const shown = name.trim() || left ? error : undefined;
  return (
    <TextField
      id="name"
      label="New family name"
      flag="--name"
      className="h-9 text-base md:text-base"
      value={name}
      placeholder={`e.g. ${family.replace(/ Variable$/, "")} Custom`}
      error={shown}
      description="Your build installs next to the original under this name. Copyright and license notices stay."
      onChange={(value) => setForm({ name: value })}
      onBlur={() => setLeft(true)}
    />
  );
}

/** A closed-by-default group inside a section, opened when something in it is set. */
function More({ title, set, children }: { title: string; set: boolean; children: ReactNode }) {
  const [initiallyOpen] = useState(set);
  return (
    <Collapsible defaultOpen={initiallyOpen}>
      <CollapsibleTrigger className="group flex cursor-pointer items-center gap-1.5 rounded-md text-sm text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50">
        <ChevronRightIcon className="size-3.5 transition-transform group-data-panel-open:rotate-90" />
        {title}
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 pt-3">{children}</CollapsibleContent>
    </Collapsible>
  );
}

/** Fonts with more features than this get a search field. */
const SEARCH_FROM = 9;

function Features({ fonts }: { fonts: ReadFont[] }) {
  const form = useStore((s) => s.form);
  const setForm = useStore((s) => s.setForm);
  const [query, setQuery] = useState("");
  const search = useRef<HTMLInputElement>(null);
  const infos = fonts.map((f) => f.info);
  const features = featureList(infos);
  const languages = [...new Set(infos.flatMap((info) => info.languages))].toSorted();

  // Every word has to be in the name or the tag: "ss02", "zero", "broken equals".
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  const searching = words.length > 0;
  const found = features.filter((f) => words.every((word) => `${f.label} ${f.tag}`.toLowerCase().includes(word)));
  const optional = found.filter((f) => f.kind === "optional");
  // A search looks through the rarely changed ones too, instead of leaving them folded away.
  const onByDefault = found.filter((f) => f.kind === "default" && (searching || !f.shaping));
  const shaping = searching ? [] : found.filter((f) => f.shaping);

  const toggle = (feature: Feature, checked: boolean) => {
    const set = feature.kind === "optional" ? "freeze" : "disable";
    // Optional: checked = freeze it on. On by default: unchecked = turn it off.
    const add = feature.kind === "optional" ? checked : !checked;
    const tags = new Set(form[set]);
    if (add) tags.add(feature.tag);
    else tags.delete(feature.tag);
    setForm({ [set]: [...tags] });
  };
  const row = (feature: Feature) => {
    const checked =
      feature.kind === "optional" ? form.freeze.includes(feature.tag) : !form.disable.includes(feature.tag);
    return (
      <li key={feature.tag}>
        <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-1.5 py-1 hover:bg-accent">
          <Checkbox checked={checked} onCheckedChange={(value) => toggle(feature, value)} />
          <span className="min-w-0 flex-1 truncate text-sm">{feature.label}</span>
          {feature.kind === "optional" && <Sample feature={feature} fonts={fonts} />}
          <span className="flag">{feature.tag}</span>
        </label>
      </li>
    );
  };
  const items = [{ value: null, label: "None" }, ...languages.map((tag) => ({ value: tag, label: languageName(tag) }))];
  const changed = form.freeze.length + form.disable.length + (form.language ? 1 : 0);
  const clear = () => {
    setQuery("");
    search.current?.focus();
  };

  return (
    <Section title="Features" summary={changed ? `${changed} changed` : undefined}>
      {features.length >= SEARCH_FROM && (
        <InputGroup>
          <InputGroupAddon>
            <SearchIcon />
          </InputGroupAddon>
          <InputGroupInput
            ref={search}
            aria-label="Search features"
            placeholder="Search features, e.g. zero or ss02"
            value={query}
            spellCheck={false}
            autoComplete="off"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Escape" && query) clear();
            }}
          />
          {query && (
            <InputGroupAddon align="inline-end">
              <InputGroupButton size="icon-xs" aria-label="Clear search" onClick={clear}>
                <XIcon />
              </InputGroupButton>
            </InputGroupAddon>
          )}
        </InputGroup>
      )}
      {searching && !found.length && (
        <p className="text-sm text-muted-foreground" aria-live="polite">
          No feature matches &ldquo;{query.trim()}&rdquo;.
        </p>
      )}
      {optional.length > 0 && (
        <div>
          <p className="text-sm font-medium">Make default</p>
          <p className="mb-2 text-xs text-muted-foreground">
            Checked features become the font&apos;s own glyphs, in every app. <span className="flag">--features</span>
          </p>
          <ul className="max-h-72 space-y-0.5 overflow-y-auto pr-1">{optional.map(row)}</ul>
        </div>
      )}
      {onByDefault.length > 0 && (
        <div>
          <p className="text-sm font-medium">On by default</p>
          <p className="mb-2 text-xs text-muted-foreground">
            Uncheck to turn a feature off, e.g. ligatures in a coding font. <span className="flag">--disable</span>
          </p>
          <ul className="space-y-0.5">{onByDefault.map(row)}</ul>
        </div>
      )}
      {languages.length > 0 && !searching && (
        <More title="Language forms" set={Boolean(form.language)}>
          <Field className="gap-1.5">
            <FieldLabel htmlFor="language" className="w-full">
              <FlagLabel text="Language" flag="--language" />
            </FieldLabel>
            <Select
              items={items}
              value={form.language || null}
              onValueChange={(value: string | null) => setForm({ language: value ?? "" })}
            >
              <SelectTrigger id="language" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {items.map((item) => (
                  <SelectItem key={item.label} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldDescription className="text-xs">
              Makes this language&apos;s letter forms the default, e.g. Romanian ș ț with a comma below.
            </FieldDescription>
          </Field>
        </More>
      )}
      {shaping.length > 0 && (
        <More
          title="Text shaping features (rarely changed)"
          set={shaping.some((f) => form.disable.includes(f.tag) || form.freeze.includes(f.tag))}
        >
          <ul className="space-y-0.5">{shaping.map(row)}</ul>
        </More>
      )}
    </Section>
  );
}

const plain = (cp: number) => /[0-9A-Za-z]/.test(String.fromCodePoint(cp));

/** The characters a feature swaps that can be shown alone, plain letters and digits first. */
function shownCharacters(codepoints: number[]): number[] {
  const visible = codepoints.filter((cp) => cp > 0x20 && cp !== 0xa0 && !/\p{M}/u.test(String.fromCodePoint(cp)));
  return visible.toSorted((a, b) => Number(plain(b)) - Number(plain(a)) || a - b);
}

/** The characters that show best what a feature swaps: its first one or two letters or
 * digits ("Il"), since their accented and superscript forms change the same way and only
 * add noise; without any, its first other character. */
export function sampleCharacters(codepoints: number[]): string {
  const shown = shownCharacters(codepoints);
  const letters = shown.filter(plain).slice(0, 2);
  return (letters.length ? letters : shown.slice(0, 1)).map((cp) => String.fromCodePoint(cp)).join("");
}

/** How many characters the large sample shows before "+ N more". */
const LARGE_SAMPLE = 8;
const SAMPLE_BOX = "inline-flex h-6 min-w-6 items-center justify-center rounded-md px-1";

/** What freezing a feature does, shown in the font itself: "0 → 0" with the slashed zero,
 * and the same larger in a card on hover, tap or Enter. Only for features that swap single
 * characters (fontmint lists those); ligatures and other rules that depend on the text
 * around them have no one sample. */
function Sample({ feature, fonts }: { feature: Feature; fonts: ReadFont[] }) {
  const previewAxes = useStore((s) => s.previewAxes);
  const font = fonts.find((f) => f.face && f.info.changes[feature.tag]?.length);
  const all = font ? shownCharacters(font.info.changes[feature.tag]!) : [];
  if (!font || !all.length) return null;
  // At the preview's axis values, so the sample has the weight the preview shows.
  const location = Object.fromEntries(font.info.axes.map(([tag, , value]) => [tag, previewAxes[tag] ?? value]));
  const original = { fontFamily: `"${font.face}"`, fontVariationSettings: variationSettings(location) };
  const changed = {
    ...original,
    fontFeatureSettings: featureSettings({ freeze: [feature.tag], disable: [], language: "" }),
  };
  const text = sampleCharacters(all);
  const large = all.slice(0, LARGE_SAMPLE);
  return (
    <Popover>
      <PopoverTrigger
        openOnHover
        delay={200}
        aria-label={`Show what ${feature.label} changes`}
        className="flex shrink-0 cursor-zoom-in items-center gap-1 rounded-md px-1 py-0.5 text-lg leading-none outline-none hover:bg-secondary focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        {/* Both sides in the same fixed box, so a small or raised glyph (², ₂) gets the same
            roomy tint as a capital, and before and after sit level. */}
        <span className={cn(SAMPLE_BOX, "text-muted-foreground")} style={original}>
          {text}
        </span>
        <ArrowRightIcon className="size-3 text-muted-foreground" />
        <span className={cn(SAMPLE_BOX, "bg-(--mark)")} style={changed}>
          {text}
        </span>
      </PopoverTrigger>
      <PopoverContent side="left" align="center" className="w-auto max-w-[calc(100vw-2rem)] gap-3 p-4">
        <PopoverHeader>
          <PopoverTitle>{feature.label}</PopoverTitle>
          <PopoverDescription className="text-xs">
            Changes {all.length} {all.length === 1 ? "character" : "characters"}
            {all.length > large.length && `; the first ${large.length} are shown`}.
          </PopoverDescription>
        </PopoverHeader>
        {/* Labeled rows, the changed one on the preview's mark color, so before and after
            can't be mixed up. Cells have no gap between them, so the row's tint is one band. */}
        <div
          className="grid items-center overflow-x-auto"
          style={{ gridTemplateColumns: `auto repeat(${large.length}, auto)` }}
        >
          <span className="eyebrow py-2 pr-3 pl-2">Original</span>
          {large.map((cp) => (
            <span
              key={cp}
              className="px-2 py-2 text-center text-5xl leading-none text-muted-foreground"
              style={original}
            >
              {String.fromCodePoint(cp)}
            </span>
          ))}
          <span className="eyebrow rounded-l-lg bg-(--mark) py-2 pr-3 pl-2 text-foreground">
            With <span className="font-mono normal-case">{feature.tag}</span>
          </span>
          {large.map((cp, i) => (
            <span
              key={cp}
              className={cn(
                "bg-(--mark) px-2 py-2 text-center text-5xl leading-none",
                i === large.length - 1 && "rounded-r-lg",
              )}
              style={changed}
            >
              {String.fromCodePoint(cp)}
            </span>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}

function Spacing({ infos, errors }: { infos: FontInfo[]; errors: FormErrors }) {
  const form = useStore((s) => s.form);
  const setForm = useStore((s) => s.setForm);
  const summary = [
    form.lineHeight.trim() && `line height ${form.lineHeight.trim()}`,
    form.letterSpacing.trim() && `spacing ${form.letterSpacing.trim()}`,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Section title="Spacing" defaultOpen={false} summary={summary || undefined}>
      <TextField
        id="line-height"
        label="Line height"
        flag="--line-height"
        inputMode="decimal"
        value={form.lineHeight}
        placeholder={infos[0]!.line_height.toFixed(2)}
        error={errors.lineHeight}
        description="× font size, 0.5–3"
        onChange={(lineHeight) => setForm({ lineHeight })}
      />
      <TextField
        id="letter-spacing"
        label="Letter spacing"
        flag="--letter-spacing"
        inputMode="decimal"
        value={form.letterSpacing}
        placeholder="0"
        error={errors.letterSpacing}
        description="em, −0.5–1"
        onChange={(letterSpacing) => setForm({ letterSpacing })}
      />
    </Section>
  );
}

function Characters({ errors }: { errors: FormErrors }) {
  const form = useStore((s) => s.form);
  const setForm = useStore((s) => s.setForm);
  const ranges = form.subsetRanges.trim();
  const kept = [...form.subset, ranges && "ranges"].filter(Boolean);
  const summary = kept.length > 2 ? `${kept.length} selected` : kept.join(", ");
  return (
    <Section title="Characters" defaultOpen={false} summary={summary || undefined}>
      <div>
        <p className="text-sm font-medium">Keep only</p>
        <p className="mb-2 text-xs text-muted-foreground">
          For smaller web fonts. None selected keeps every character. <span className="flag">--subset</span>
        </p>
        <ToggleGroup
          aria-label="Character sets to keep"
          multiple
          variant="outline"
          size="sm"
          className="flex-wrap"
          value={form.subset}
          onValueChange={(subset: string[]) => setForm({ subset })}
        >
          {SUBSETS.map((subset) => (
            <ToggleGroupItem
              key={subset}
              value={subset}
              className="font-mono text-xs data-pressed:border-primary data-pressed:bg-primary data-pressed:text-primary-foreground"
            >
              {subset}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        {form.subset.length > 0 && !form.subset.includes("latin") && (
          <p className="mt-2 text-xs text-muted-foreground">
            Only latin has digits, punctuation and the space - add it to the others.
          </p>
        )}
      </div>
      <TextField
        id="subset-ranges"
        label="More characters"
        className="font-mono"
        value={form.subsetRanges}
        placeholder="U+2190-21FF, U+20AC"
        error={errors.subsetRanges}
        description="Unicode ranges, separated by commas."
        onChange={(subsetRanges) => setForm({ subsetRanges })}
      />
    </Section>
  );
}

function Output({ infos, errors }: { infos: FontInfo[]; errors: FormErrors }) {
  const form = useStore((s) => s.form);
  const setForm = useStore((s) => s.setForm);
  const variable = infos.filter((info) => info.variable);
  const cff2 = variable.some((info) => info.cff2);
  const truetype = variable.some((info) => !info.cff2);
  const axes = axisRanges(variable);
  const instances = Math.max(...infos.map((info) => info.instances.length));
  const custom = form.styles.some((style) => style.name.trim() || Object.values(style.axes).some((v) => v.trim()));
  const several = form.styles.length > 1;
  const setStyle = (row: number, change: Partial<Style>) =>
    setForm({ styles: form.styles.map((style, i) => (i === row ? { ...style, ...change } : style)) });

  return (
    <Section title="Output">
      <Field data-invalid={Boolean(errors.formats)} className="gap-1.5">
        <p className="w-full text-sm font-medium">
          <FlagLabel text="Formats" flag="--formats" />
        </p>
        <div className="flex gap-5">
          {(
            [
              ["own", cff2 && truetype ? "TTF / OTF" : cff2 ? "OTF" : "TTF"],
              ["woff2", "WOFF2"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex cursor-pointer items-center gap-2 text-sm">
              <Checkbox
                checked={form.formats[key]}
                aria-invalid={Boolean(errors.formats)}
                onCheckedChange={(checked) => setForm({ formats: { ...form.formats, [key]: checked } })}
              />
              {label}
            </label>
          ))}
        </div>
        {errors.formats && <FieldError className="text-xs">{errors.formats}</FieldError>}
      </Field>
      <Field data-invalid={Boolean(errors.staticFonts)} className="gap-1.5">
        <div className="flex items-start gap-2.5">
          <Switch
            id="static-fonts"
            className="mt-0.5"
            checked={form.staticFonts}
            aria-invalid={Boolean(errors.staticFonts)}
            onCheckedChange={(staticFonts) => setForm({ staticFonts })}
          />
          <label htmlFor="static-fonts" className="cursor-pointer text-sm">
            Static fonts too <span className="flag">{form.staticFonts ? "" : "--no-static"}</span>
            <span className="block text-xs text-muted-foreground">
              {cff2 && !truetype
                ? "Not available for CFF2 (OTF) variable fonts yet; only the variable font is built."
                : `One file per style: without axis values, the font's ${instances} named styles.`}
            </span>
          </label>
        </div>
        {errors.staticFonts && <FieldError className="text-xs">{errors.staticFonts}</FieldError>}
      </Field>
      <More title="Axis values and style names" set={custom}>
        <p className="text-xs text-muted-foreground">
          Single values make static fonts (e.g. 375), ranges make a smaller variable font (300:700), &quot;all&quot;
          uses the named styles. Separate several with commas.
        </p>
        {form.styles.map((style, row) => (
          <fieldset
            // oxlint-disable-next-line react/no-array-index-key -- rows have no identity but their place
            key={row}
            aria-label={several ? `Style ${row + 1}` : undefined}
            className={several ? "space-y-3 rounded-xl border p-3" : "space-y-3"}
          >
            {several && (
              <div className="flex items-center justify-between">
                <p className="eyebrow">Style {row + 1}</p>
                <Button
                  variant="ghost"
                  size="icon-xs"
                  aria-label={`Remove style ${row + 1}`}
                  onClick={() => setForm({ styles: form.styles.filter((_, i) => i !== row) })}
                >
                  <XIcon />
                </Button>
              </div>
            )}
            {[...axes].map(([tag, [min, max]]) => {
              const [label, flag] = AXIS_NAMES[tag] ?? [tag, `--axis ${tag}=`];
              return (
                <TextField
                  key={tag}
                  id={`axis-${row}-${tag}`}
                  label={`${label} (${min}–${max})`}
                  flag={flag}
                  className="font-mono"
                  value={style.axes[tag] ?? ""}
                  placeholder={tag === "wght" ? "e.g. 375 or 400,700 or 300:700" : "e.g. all"}
                  error={errors[`axis-${row}-${tag}`]}
                  onChange={(value) => setStyle(row, { axes: { ...style.axes, [tag]: value } })}
                />
              );
            })}
            <TextField
              id={`style-${row}`}
              label="Style name"
              flag="--style-name"
              value={style.name}
              placeholder={row === 1 ? "e.g. Bold" : "e.g. Regular"}
              error={errors[`style-${row}`]}
              description={
                row === 0 ? "Names the one static font these values make, e.g. weight 375 as Regular." : undefined
              }
              onChange={(name) => setStyle(row, { name })}
            />
          </fieldset>
        ))}
        <div className="space-y-1.5">
          <Button variant="outline" size="sm" onClick={() => setForm({ styles: [...form.styles, emptyStyle] })}>
            <PlusIcon />
            Add another style
          </Button>
          <p className="text-xs text-muted-foreground">
            For several named fonts in one build, e.g. 375 as Regular and 675 as Bold.
          </p>
        </div>
      </More>
      <CliNote className="mt-1" />
    </Section>
  );
}
