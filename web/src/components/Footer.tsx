import { useEffect, useState } from "react";
import type { Manifest } from "../lib/types";
import { LockIcon } from "lucide-react";
import { REPO } from "./ui";

export function Footer() {
  const [manifest, setManifest] = useState<Manifest | null>(null);
  useEffect(() => {
    fetch("manifest.json")
      .then((response) => (response.ok ? response.json() : null))
      .then(setManifest)
      .catch(() => {});
  }, []);

  const link = "underline decoration-border underline-offset-3 hover:text-foreground";
  return (
    <footer className="mx-auto mt-16 w-full max-w-6xl px-4 pb-10 sm:px-6">
      <div className="flex flex-col gap-3 border-t pt-6 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p>
          Built by{" "}
          <a href="https://github.com/svipas" className={link}>
            Benas Svipas
          </a>{" "}
          ·{" "}
          <a href={REPO} className={link}>
            GitHub
          </a>
          {manifest && (
            <>
              {" "}
              ·{" "}
              <a
                href={`${REPO}/commit/${manifest.commit}`}
                title={`Built from commit ${manifest.commit}`}
                className={`${link} font-mono text-xs`}
              >
                v{manifest.site}
              </a>
            </>
          )}
        </p>
        <p className="flex items-center gap-1.5">
          <LockIcon className="size-3.5" aria-hidden="true" />
          Fonts never leave your computer
        </p>
      </div>
    </footer>
  );
}
