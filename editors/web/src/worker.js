// عامل التنفيذ المعزول: يحمّل وحدة WebAssembly ويشغّل كود المستخدم بعيدًا عن
// واجهة المحرر. إن علِق البرنامج (حلقة لا تنتهي) تُنهي الصفحةُ هذا العامل كليًا.
let exportsP = null;

function load(url) {
  exportsP ??= WebAssembly.instantiateStreaming(fetch(url), {
    env: { dhad_now_ms: () => performance.now() },
  }).then((r) => r.instance.exports);
  return exportsP;
}

const enc = new TextEncoder();
const dec = new TextDecoder();

function call(x, fn, src, ...rest) {
  const bytes = enc.encode(src);
  const p = x.dhad_alloc(bytes.length);
  new Uint8Array(x.memory.buffer, p, bytes.length).set(bytes);
  const n = x[fn](p, bytes.length, ...rest);
  x.dhad_free(p, bytes.length);
  return JSON.parse(dec.decode(new Uint8Array(x.memory.buffer, x.dhad_result_ptr(), n)));
}

function resultBytes(x, n) {
  return new Uint8Array(x.memory.buffer, x.dhad_result_ptr(), n).slice();
}

// تشغيل وحدة مترجمة من برنامج المستخدم، مع التقاط المطبوعات.
function runCompiled(bytes) {
  let out = "";
  let memory;
  const instance = new WebAssembly.Instance(new WebAssembly.Module(bytes), {
    env: {
      print_i64: (v) => { out += v.toString(); },
      print_bool: (b) => { out += b ? "صحيح" : "خطأ"; },
      print_str: (ptr, len) => { out += dec.decode(new Uint8Array(memory.buffer, ptr, len)); },
      print_newline: () => { out += "\n"; },
      fail: (code) => { const err = new Error("fail"); err.dhadCode = code; throw err; },
    },
  });
  memory = instance.exports.memory;
  try {
    instance.exports.run();
    return { output: out };
  } catch (err) {
    return { output: out, failCode: err.dhadCode ?? null, trap: err.dhadCode ? null : String(err.message || err) };
  }
}

self.onmessage = async (e) => {
  const { id, kind, src, fuel, code, wasmUrl } = e.data;
  try {
    const x = await load(wasmUrl);
    let result;
    if (kind === "run") result = call(x, "dhad_run", src, fuel || 0);
    else if (kind === "check") result = call(x, "dhad_check", src);
    else if (kind === "compile-run" || kind === "wat") {
      const bytes = enc.encode(src);
      const p = x.dhad_alloc(bytes.length);
      new Uint8Array(x.memory.buffer, p, bytes.length).set(bytes);
      const t0 = performance.now();
      const n = (kind === "wat" ? x.dhad_compile_wat : x.dhad_compile)(p, bytes.length);
      const compileMs = performance.now() - t0;
      x.dhad_free(p, bytes.length);
      const raw = resultBytes(x, n);
      const isWasm = raw[0] === 0 && raw[1] === 0x61 && raw[2] === 0x73 && raw[3] === 0x6d;
      if (kind === "wat" || !isWasm) {
        result = JSON.parse(dec.decode(raw));
      } else {
        const t1 = performance.now();
        const r = runCompiled(raw);
        result = { ok: !r.failCode && !r.trap, ...r, compileMs, runMs: performance.now() - t1, size: raw.length };
      }
    }
    else if (kind === "explain") {
      const n = x.dhad_explain(code);
      result = JSON.parse(dec.decode(new Uint8Array(x.memory.buffer, x.dhad_result_ptr(), n)));
    }
    self.postMessage({ id, result });
  } catch (err) {
    self.postMessage({ id, crash: String(err && err.message || err) });
  }
};
