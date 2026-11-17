import { MonitorIcon, MoonIcon, SunIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { applyTheme, saveTheme, storedTheme, systemDark, type Theme } from "@/lib/theme";

const THEMES = [
  ["system", "System theme", MonitorIcon],
  ["light", "Light theme", SunIcon],
  ["dark", "Dark theme", MoonIcon],
] as const;

export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(storedTheme);

  useEffect(() => {
    if (theme !== "system") return;
    const media = systemDark();
    const update = () => applyTheme("system");
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, [theme]);

  return (
    <ToggleGroup
      aria-label="Theme"
      size="sm"
      spacing={0}
      variant="outline"
      value={[theme]}
      onValueChange={(value: string[]) => {
        const next = value[0] as Theme | undefined;
        if (!next) return;
        setTheme(next);
        saveTheme(next);
      }}
    >
      {THEMES.map(([value, label, Icon]) => (
        <ToggleGroupItem key={value} value={value} aria-label={label} title={label}>
          <Icon />
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  );
}
