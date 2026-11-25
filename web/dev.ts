// Development server: bun --hot dev.ts
// Bun's HTML bundling doesn't follow `new Worker(...)`, so the worker gets its own
// route, built on request. Everything else comes from public/ (bun scripts/assets.ts).
import { join, normalize } from "node:path";
import index from "./src/index.html";

const pub = join(import.meta.dir, "public");

const server = Bun.serve({
  port: Number(process.env.PORT ?? 3000),
  development: { hmr: true, console: true },
  routes: {
    "/": index,
    "/worker.js": async () => {
      const build = await Bun.build({
        entrypoints: ["./src/worker.ts"],
        target: "browser",
        define: { MANIFEST: await Bun.file(join(pub, "manifest.json")).text() },
      });
      if (!build.success) return new Response(build.logs.join("\n"), { status: 500 });
      return new Response(build.outputs[0], { headers: { "Content-Type": "text/javascript" } });
    },
  },
  async fetch(request) {
    const path = normalize(decodeURIComponent(new URL(request.url).pathname));
    const file = Bun.file(join(pub, path));
    if (!path.startsWith("/") || path.includes("..") || !(await file.exists()))
      return new Response("Not found", { status: 404 });
    return new Response(file);
  },
});

console.log(`fontmint dev server: ${server.url}`);
