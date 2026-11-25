// Production build into dist/: the worker (on its own, since Bun doesn't bundle workers it
// finds in code), the page that starts it and everything in public/.
import { cp, rm } from "node:fs/promises";
import { basename, join } from "node:path";
import type { BuildConfig } from "bun";
import tailwind from "bun-plugin-tailwind";

const web = import.meta.dir;
const dist = join(web, "dist");

await rm(dist, { recursive: true, force: true });

async function build(entry: string, entryName: string, define: Record<string, unknown>, config?: Partial<BuildConfig>) {
  const result = await Bun.build({
    entrypoints: [join(web, "src", entry)],
    outdir: dist,
    target: "browser",
    minify: true,
    sourcemap: "linked",
    define: Object.fromEntries(Object.entries(define).map(([name, value]) => [name, JSON.stringify(value)])),
    naming: { entry: entryName, chunk: "[name]-[hash].[ext]", asset: "[name]-[hash].[ext]" },
    publicPath: "./",
    ...config,
  });
  if (!result.success) {
    console.error(result.logs.join("\n"));
    process.exit(1);
  }
  return result.outputs;
}

// The page names its worker, and the worker what it loads, so a browser never mixes a cached
// file with those of another deploy (GitHub Pages lets it keep each for 10 minutes).
const MANIFEST = await Bun.file(join(web, "public", "manifest.json")).json();
const worker = await build("worker.ts", "[name]-[hash].[ext]", { MANIFEST });
const page = await build(
  "index.html",
  "[name].[ext]",
  {
    WORKER: basename(worker.find((output) => output.kind === "entry-point")!.path),
    "process.env.NODE_ENV": "production",
  },
  { reactCompiler: true, plugins: [tailwind] },
);
// public/samples/ holds fonts for trying the page locally; they're not part of the site.
const samples = join(web, "public", "samples");
await cp(join(web, "public"), dist, { recursive: true, filter: (source) => !source.startsWith(samples) });
for (const output of [...worker, ...page])
  console.log(`${(output.size / 1024).toFixed(1).padStart(8)} KB  ${output.path.slice(dist.length + 1)}`);
