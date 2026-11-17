// Production build into dist/: the page, the worker (its own entry point, since Bun
// doesn't bundle workers it finds in code) and everything in public/.
import { cp, rm } from "node:fs/promises";
import { join } from "node:path";
import tailwind from "bun-plugin-tailwind";

const web = import.meta.dir;
const dist = join(web, "dist");

await rm(dist, { recursive: true, force: true });
const result = await Bun.build({
  entrypoints: [join(web, "src/index.html"), join(web, "src/worker.ts")],
  outdir: dist,
  target: "browser",
  minify: true,
  sourcemap: "linked",
  reactCompiler: true,
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  naming: { entry: "[name].[ext]", chunk: "[name]-[hash].[ext]", asset: "[name]-[hash].[ext]" },
  publicPath: "./",
  plugins: [tailwind],
});
if (!result.success) {
  console.error(result.logs.join("\n"));
  process.exit(1);
}
// public/samples/ holds fonts for trying the page locally; they're not part of the site.
const samples = join(web, "public", "samples");
await cp(join(web, "public"), dist, { recursive: true, filter: (source) => !source.startsWith(samples) });
for (const output of result.outputs)
  console.log(`${(output.size / 1024).toFixed(1).padStart(8)} KB  ${output.path.slice(dist.length + 1)}`);
