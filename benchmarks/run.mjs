// قياس الأداء والاختبار التفاضلي لمساري التنفيذ في ضاد.
//
// لكل برنامج في benchmarks/programs:
//   ١) المفسر الأصلي (dhad شغّل، بناء release)
//   ٢) المفسر نفسه مترجمًا إلى WebAssembly (كما يعمل في الساحة)
//   ٣) البرنامج مترجمًا بمولّد WebAssembly (dhad ترجم)
// يجب أن تتطابق المخرجات الثلاثة حرفيًا، ثم يُقاس الزمن (الوسيط من عدة تكرارات).
//
// الاستخدام: node benchmarks/run.mjs [--runs 7] [--check]   (--check: تحقق من التطابق فقط)
import { execFileSync, spawnSync } from "node:child_process";
import { readFileSync, readdirSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { performance } from "node:perf_hooks";
import os from "node:os";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const args = process.argv.slice(2);
const RUNS = Number(args[args.indexOf("--runs") + 1]) || 7;
const CHECK_ONLY = args.includes("--check");

console.log("◆ بناء المفسر والمولّد (release)…");
execFileSync("cargo", ["build", "--release", "-q", "-p", "dhad-cli"], { cwd: root, stdio: "inherit" });
execFileSync("cargo", ["build", "--release", "-q", "--target", "wasm32-unknown-unknown", "-p", "dhad-wasm"], { cwd: root, stdio: "inherit" });
const CLI = join(root, "target/release/dhad");
const INTERP_WASM = readFileSync(join(root, "target/wasm32-unknown-unknown/release/dhad_wasm.wasm"));

const enc = new TextEncoder();
const dec = new TextDecoder();

// ---- ٢) المفسر داخل WebAssembly ----
const interp = (await WebAssembly.instantiate(INTERP_WASM, { env: { dhad_now_ms: () => performance.now() } })).instance.exports;
function runInterpWasm(src) {
  const b = enc.encode(src);
  const p = interp.dhad_alloc(b.length);
  new Uint8Array(interp.memory.buffer, p, b.length).set(b);
  const n = interp.dhad_run(p, b.length, 0);
  interp.dhad_free(p, b.length);
  const r = JSON.parse(dec.decode(new Uint8Array(interp.memory.buffer, interp.dhad_result_ptr(), n)));
  if (r.error) throw new Error(r.error.rendered);
  return r.output;
}

// ---- ٣) البرنامج المترجم ----
export function instantiateCompiled(bytes) {
  let out = "";
  let memory;
  const instance = new WebAssembly.Instance(new WebAssembly.Module(bytes), {
    env: {
      print_i64: (v) => { out += v.toString(); },
      print_bool: (b) => { out += b ? "صحيح" : "خطأ"; },
      print_str: (ptr, len) => { out += dec.decode(new Uint8Array(memory.buffer, ptr, len)); },
      print_newline: () => { out += "\n"; },
      fail: (code) => { throw new Error(`ضاد-${code}`); },
    },
  });
  memory = instance.exports.memory;
  return { run: () => { out = ""; instance.exports.run(); return out; } };
}

function median(xs) {
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

function time(fn, runs) {
  const ts = [];
  let result;
  for (let i = 0; i < runs; i++) {
    const t0 = performance.now();
    result = fn();
    ts.push(performance.now() - t0);
  }
  return { ms: median(ts), result };
}

// programs/: تُقاس وتُتحقق؛ conformance/: حالات حدية تُتحقق فقط (أقصر من أن تُقاس).
const list = (dir) => readdirSync(join(here, dir)).filter((f) => f.endsWith(".ضاد")).sort().map((f) => [dir, f]);
const files = [...list("conformance"), ...list("programs")];
const rows = [];
let mismatches = 0;

for (const [dir, f] of files) {
  const path = join(here, dir, f);
  const src = readFileSync(path, "utf8");
  const name = basename(f, ".ضاد");

  const wasmPath = join(os.tmpdir(), `dhad-bench-${process.pid}.wasm`);
  execFileSync(CLI, ["ترجم", path, "-o", wasmPath], { stdio: ["ignore", "ignore", "pipe"] });
  const compiled = instantiateCompiled(readFileSync(wasmPath));

  const nativeOnce = () => {
    const r = spawnSync(CLI, ["شغّل", path], { encoding: "utf8" });
    if (r.status !== 0) throw new Error(r.stderr);
    return r.stdout;
  };

  const a = nativeOnce();
  const b = runInterpWasm(src);
  const c = compiled.run();
  const same = a === b && b === c;
  if (!same) {
    mismatches++;
    console.log(`✘ ${name}: المخرجات غير متطابقة\n  مفسر أصلي: ${JSON.stringify(a)}\n  مفسر WASM: ${JSON.stringify(b)}\n  مترجم:      ${JSON.stringify(c)}`);
  } else {
    console.log(`✔ ${name}: المخرجات متطابقة في المسارات الثلاثة`);
  }
  if (CHECK_ONLY || dir === "conformance") continue;

  const native = time(nativeOnce, RUNS);
  const interpWasm = time(() => runInterpWasm(src), RUNS);
  const comp = time(() => compiled.run(), Math.max(RUNS, 15));
  rows.push({
    program: name,
    native_interpreter_ms: +native.ms.toFixed(2),
    wasm_interpreter_ms: +interpWasm.ms.toFixed(2),
    compiled_wasm_ms: +comp.ms.toFixed(3),
    speedup_vs_native: +(native.ms / comp.ms).toFixed(1),
    speedup_vs_wasm_interpreter: +(interpWasm.ms / comp.ms).toFixed(1),
    wasm_bytes: readFileSync(wasmPath).length,
  });
}

if (mismatches) {
  console.error(`✘ ${mismatches} برنامج بمخرجات غير متطابقة`);
  process.exit(1);
}
if (CHECK_ONLY) process.exit(0);

const env = {
  date: new Date().toISOString().slice(0, 10),
  node: process.version,
  cpu: os.cpus()[0]?.model ?? "غير معروف",
  cores: os.cpus().length,
  platform: `${os.platform()} ${os.arch()}`,
  runs: RUNS,
};
const outDir = join(here, "results");
mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, "latest.json"), JSON.stringify({ env, rows }, null, 2) + "\n");

const geo = (k) => Math.exp(rows.reduce((s, r) => s + Math.log(r[k]), 0) / rows.length);
const md = [
  "# نتائج قياس الأداء",
  "",
  `البيئة: ${env.platform}، ${env.cpu} (${env.cores} أنوية)، Node ${env.node}، ${env.date}. الوسيط من ${RUNS} تكرارات.`,
  "",
  "| البرنامج | المفسر الأصلي (ms) | المفسر في WASM (ms) | المترجم إلى WASM (ms) | التسريع مقابل الأصلي | التسريع مقابل مفسر WASM | حجم الوحدة (بايت) |",
  "|---|---:|---:|---:|---:|---:|---:|",
  ...rows.map((r) => `| ${r.program} | ${r.native_interpreter_ms} | ${r.wasm_interpreter_ms} | ${r.compiled_wasm_ms} | ×${r.speedup_vs_native} | ×${r.speedup_vs_wasm_interpreter} | ${r.wasm_bytes} |`),
  "",
  `**المتوسط الهندسي للتسريع:** ×${geo("speedup_vs_native").toFixed(1)} مقابل المفسر الأصلي، و×${geo("speedup_vs_wasm_interpreter").toFixed(1)} مقابل المفسر في WASM.`,
  "",
  "ملاحظات منهجية:",
  "- زمن المفسر الأصلي يشمل بدء العملية (عادةً ١–٢ ms)؛ المساران الآخران يُقاسان داخل عملية Node واحدة بعد التحميل.",
  "- زمن ترجمة البرنامج إلى WASM لا يدخل في القياس (يُترجم مرة واحدة)، وكذلك تحميل الوحدة.",
  "- قبل أي قياس يُتحقق من تطابق المخرجات حرفيًا في المسارات الثلاثة.",
  "",
];
writeFileSync(join(outDir, "latest.md"), md.join("\n"));
console.log("\n" + md.slice(4, 4 + rows.length + 3).join("\n"));
