// Puts everything the worker loads at runtime into public/: the Pyodide core with the
// package fontmint needs, and all Python code (the standard library, the pinned fontTools
// and a freshly built fontmint) compiled into one zip. The site serves these itself; no
// CDN or PyPI request happens in the browser.
import { mkdir, rm } from "node:fs/promises";
import { join } from "node:path";
import bundleSource from "./bundle.py" with { type: "text" };

const PYODIDE = "314.0.8";
const PYODIDE_CORE = {
  url: `https://github.com/pyodide/pyodide/releases/download/${PYODIDE}/pyodide-core-${PYODIDE}.tar.bz2`,
  sha256: "ff3e5f9d9bc8e98ff30b99515535fc24d375994f47a978c61975d653e162ca37",
};
const PYODIDE_FILES = ["pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"];
const PYODIDE_PACKAGES = ["brotli"];
// Pyodide's own fontTools is too old for fontmint, so a newer pure-Python wheel is pinned.
const FONTTOOLS = {
  file: "fonttools-4.69.1-py3-none-any.whl",
  url: "https://files.pythonhosted.org/packages/43/ef/3575cacafe63d7d78b639e815bb3637cd0a66c6365efc5aed636a92cdb12/fonttools-4.69.1-py3-none-any.whl",
  sha256: "20e9dfac71694d9eeae48bb53c877bdf43b914794d69a769940728a1929cc835",
};

const web = join(import.meta.dir, "..");
const repo = join(web, "..");
const cache = join(web, ".cache");
const pub = join(web, "public");
const core = join(pub, "pyodide", PYODIDE);

async function download(url: string, sha256: string, path: string): Promise<Uint8Array> {
  const cached = Bun.file(path);
  if ((await cached.exists()) && hash(await cached.bytes()) === sha256) return cached.bytes();
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  const data = new Uint8Array(await response.arrayBuffer());
  if (hash(data) !== sha256) throw new Error(`${url}: checksum mismatch`);
  await Bun.write(path, data);
  return data;
}

function hash(data: Uint8Array): string {
  return new Bun.CryptoHasher("sha256").update(data).digest("hex");
}

async function run(cmd: string[], cwd: string): Promise<void> {
  const proc = Bun.spawn(cmd, { cwd, stdout: "inherit", stderr: "inherit" });
  if ((await proc.exited) !== 0) throw new Error(`${cmd.join(" ")} failed`);
}

await rm(join(pub, "pyodide"), { recursive: true, force: true });
await mkdir(core, { recursive: true });

const archive = join(cache, `pyodide-core-${PYODIDE}.tar.bz2`);
await download(PYODIDE_CORE.url, PYODIDE_CORE.sha256, archive);
await run(
  ["tar", "-xjf", archive, "--strip-components=1", "-C", core, ...PYODIDE_FILES.map((f) => `pyodide/${f}`)],
  web,
);

// Pyodide packages and their dependencies, checked against the lock file's hashes
type LockPackage = { file_name: string; sha256: string; depends: string[] };
const lockFile = Bun.file(join(core, "pyodide-lock.json"));
const lock: { packages: Record<string, LockPackage> } = await lockFile.json();
const needed = new Set<string>();
const visit = (name: string) => {
  if (needed.has(name)) return;
  const pkg = lock.packages[name];
  if (!pkg) throw new Error(`Pyodide ${PYODIDE} has no package ${name}`);
  needed.add(name);
  pkg.depends.forEach(visit);
};
PYODIDE_PACKAGES.forEach(visit);
for (const name of needed) {
  const { file_name, sha256 } = lock.packages[name]!;
  const data = await download(
    `https://cdn.jsdelivr.net/pyodide/v${PYODIDE}/full/${file_name}`,
    sha256,
    join(cache, file_name),
  );
  await Bun.write(join(core, file_name), data);
}
lock.packages = Object.fromEntries([...needed].map((name) => [name, lock.packages[name]!]));
await Bun.write(lockFile, JSON.stringify(lock));

const wheels = join(cache, "wheels");
await rm(wheels, { recursive: true, force: true });
await run(["uv", "build", "--quiet", "--wheel", "--no-create-gitignore", "--out-dir", wheels], repo);
const fontmintWheel = [...new Bun.Glob("fontmint-*.whl").scanSync(wheels)][0];
if (!fontmintWheel) throw new Error("the fontmint wheel wasn't built");

const stdlib = join(core, "python_stdlib.zip");
const { loadPyodide }: typeof import("pyodide") = await import(join(core, "pyodide.mjs"));
const pyodide = await loadPyodide({
  indexURL: `${core}/`,
  env: { PYTHONNODEBUGRANGES: "1" }, // smaller: no column numbers for tracebacks
});
const archives = {
  "stdlib.zip": await Bun.file(stdlib).bytes(),
  [FONTTOOLS.file]: await download(FONTTOOLS.url, FONTTOOLS.sha256, join(cache, FONTTOOLS.file)),
  [fontmintWheel]: await Bun.file(join(wheels, fontmintWheel)).bytes(),
};
for (const [name, data] of Object.entries(archives)) pyodide.FS.writeFile(`/tmp/${name}`, data);
pyodide.FS.writeFile("/home/pyodide/bundle.py", bundleSource);
pyodide.pyimport("bundle").bundle(
  Object.keys(archives).map((name) => `/tmp/${name}`),
  "/tmp/python.zip",
);
const bundled: Uint8Array = pyodide.FS.readFile("/tmp/python.zip");
await rm(stdlib);
const python = `pyodide/python-${hash(bundled).slice(0, 8)}.zip`;
await Bun.write(join(pub, python), bundled);

// What a worker fetches while starting (the page's download progress); Pyodide's two
// .mjs files are loaded with import(), which can't be counted.
const fetched = [
  ...["pyodide-lock.json", "pyodide.asm.wasm"].map((f) => `pyodide/${PYODIDE}/${f}`),
  python,
  ...[...needed].map((name) => `pyodide/${PYODIDE}/${lock.packages[name]!.file_name}`),
];
const commit = Bun.spawnSync(["git", "rev-parse", "--short", "HEAD"], { cwd: repo }).stdout.toString().trim();
const manifest = {
  // The website's own version (web/package.json), released with web-v* tags.
  site: (await Bun.file(join(web, "package.json")).json()).version as string,
  pyodide: PYODIDE,
  fontmint: fontmintWheel.split("-")[1],
  commit,
  python,
  downloads: Object.fromEntries(fetched.map((path) => [path, Bun.file(join(pub, path)).size])),
};
await Bun.write(join(pub, "manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
console.log(`public/: Pyodide ${PYODIDE} (${[...needed].join(", ")}), ${FONTTOOLS.file}, ${fontmintWheel}`);
