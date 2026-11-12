// بناء ساحة ضاد: ترجمة المفسر إلى WebAssembly، تجميع الأمثلة، وحزم JavaScript.
// الاستخدام: npm run build   (الناتج في editors/web/dist)
import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, writeFileSync, copyFileSync, rmSync } from "node:fs";
import { dirname, join, basename } from "node:path";
import { fileURLToPath } from "node:url";
import * as esbuild from "esbuild";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const dist = join(here, "dist");

console.log("◆ ترجمة المفسر إلى WebAssembly…");
execFileSync("cargo", ["build", "--release", "--target", "wasm32-unknown-unknown", "-p", "dhad-wasm"], { cwd: root, stdio: "inherit" });

rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });
copyFileSync(join(root, "target/wasm32-unknown-unknown/release/dhad_wasm.wasm"), join(dist, "dhad.wasm"));

console.log("◆ تجميع الأمثلة…");
const TITLES = {
  "مرحبا": "مرحبًا يا عالم",
  "الأعداد_الأولية": "الأعداد الأولية والمضروب",
  "القوائم_والقواميس": "القوائم والقواميس والنصوص",
  "فيبوناتشي": "فيبوناتشي + اختبارات",
  "خطأ_متعمد": "خطأ متعمد (جرّب التلميحات)",
  "مقارنة_الأداء": "⚡ قارن: المفسر مقابل WebAssembly",
};
const order = Object.keys(TITLES);
const examples = readdirSync(join(root, "examples"))
  .filter((f) => f.endsWith(".ضاد"))
  .map((f) => basename(f, ".ضاد"))
  .filter((id) => id in TITLES)
  .sort((a, b) => order.indexOf(a) - order.indexOf(b))
  .map((id) => ({ id, title: TITLES[id], code: readFileSync(join(root, "examples", id + ".ضاد"), "utf8") }));
writeFileSync(join(here, "src", "examples.json"), JSON.stringify(examples, null, 1));

console.log("◆ حزم JavaScript…");
const common = { bundle: true, minify: true, format: "esm", target: "es2022", legalComments: "none", logLevel: "warning" };
await esbuild.build({ ...common, entryPoints: [join(here, "src/main.js")], outfile: join(dist, "main.js") });
await esbuild.build({ ...common, entryPoints: [join(here, "src/worker.js")], outfile: join(dist, "worker.js"), format: "iife" });
copyFileSync(join(here, "index.html"), join(dist, "index.html"));
copyFileSync(join(here, "style.css"), join(dist, "style.css"));
console.log("✔ تم البناء في", dist);
