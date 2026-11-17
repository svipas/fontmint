import logo from "../../../assets/logo.svg";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { ThemeToggle } from "./ThemeToggle";
import { GitHubIcon, REPO } from "./ui";

export function Header() {
  return (
    <header className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-4 py-5 sm:px-6">
      <a href="./" className="flex items-center gap-2.5 rounded-lg">
        <img src={logo} alt="fontmint" width={122} height={40} className="h-9 w-auto" />
        <Badge
          variant="outline"
          className="border-primary/40 text-[10px] font-bold tracking-widest text-primary uppercase"
        >
          Beta
        </Badge>
      </a>
      <div className="flex items-center gap-2">
        <ThemeToggle />
        <a href={REPO} className={buttonVariants({ variant: "ghost", size: "sm" })}>
          <GitHubIcon />
          <span className="hidden sm:inline">GitHub</span>
        </a>
      </div>
    </header>
  );
}
