// Serves the production build (dist/) the way GitHub Pages does: under /fontmint/, so
// a path that only works at the domain root shows up before the deploy.
// bun scripts/serve.ts (PORT=4173 by default); the end-to-end tests start it themselves.
import { join, normalize } from "node:path";

const dist = join(import.meta.dir, "..", "dist");
const BASE = "/fontmint/";

const server = Bun.serve({
  port: Number(process.env.PORT ?? 4173),
  async fetch(request) {
    const { pathname } = new URL(request.url);
    if (pathname === "/" || pathname === BASE.slice(0, -1)) return Response.redirect(BASE, 301);
    if (!pathname.startsWith(BASE)) return new Response("Not found", { status: 404 });
    const path = normalize(decodeURIComponent(pathname.slice(BASE.length)) || "index.html");
    const file = Bun.file(join(dist, path));
    if (path.startsWith("..") || !(await file.exists())) return new Response("Not found", { status: 404 });
    return new Response(file);
  },
});

console.log(`dist/ at ${server.url.href.replace(/\/$/, "")}${BASE}`);
