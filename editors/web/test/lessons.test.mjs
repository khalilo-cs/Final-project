// يتحقق من سلامة الدروس بالمفسر الحقيقي (WebAssembly): كل حل ينجح، وكل كود بداية يفشل،
// وكل مثال في نص الدرس صحيح نحويًا.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { LESSONS, gradedSource, judge } from "../../../learn/lessons.mjs";

const wasm = readFileSync(new URL("../dist/dhad.wasm", import.meta.url));
const x = (await WebAssembly.instantiate(wasm, { env: { dhad_now_ms: () => performance.now() } })).instance.exports;
const enc = new TextEncoder(), dec = new TextDecoder();
function call(fn, src, ...rest) {
  const b = enc.encode(src); const p = x.dhad_alloc(b.length);
  new Uint8Array(x.memory.buffer, p, b.length).set(b);
  const n = x[fn](p, b.length, ...rest); x.dhad_free(p, b.length);
  return JSON.parse(dec.decode(new Uint8Array(x.memory.buffer, x.dhad_result_ptr(), n)));
}
const run = (src) => call("dhad_run", src, 5_000_000);

const ids = new Set();
for (const lesson of LESSONS) {
  assert.ok(!ids.has(lesson.id), `معرّف مكرر ${lesson.id}`);
  ids.add(lesson.id);
  const sol = judge(lesson, run(gradedSource(lesson, lesson.solution)));
  assert.ok(sol.passed, `الدرس ${lesson.id}: الحل لا ينجح ${JSON.stringify(sol)}`);
  const start = judge(lesson, run(gradedSource(lesson, lesson.starter)));
  assert.ok(!start.passed, `الدرس ${lesson.id}: كود البداية ينجح دون حل`);
  for (const block of lesson.body.join("\n").matchAll(/```dhad\n([\s\S]*?)```/g)) {
    const r = call("dhad_check", block[1]);
    const syntax = (r.diagnostics || []).filter((d) => d.code < 1000);
    assert.deepEqual(syntax, [], `الدرس ${lesson.id}: مثال غير صحيح نحويًا:\n${block[1]}`);
  }
}
console.log(`✔ الدروس: ${LESSONS.length} درسًا — كل حل ينجح، وكل بداية تفشل، وكل الأمثلة صحيحة`);
