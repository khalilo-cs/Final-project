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

self.onmessage = async (e) => {
  const { id, kind, src, fuel, code, wasmUrl } = e.data;
  try {
    const x = await load(wasmUrl);
    let result;
    if (kind === "run") result = call(x, "dhad_run", src, fuel || 0);
    else if (kind === "check") result = call(x, "dhad_check", src);
    else if (kind === "explain") {
      const n = x.dhad_explain(code);
      result = JSON.parse(dec.decode(new Uint8Array(x.memory.buffer, x.dhad_result_ptr(), n)));
    }
    self.postMessage({ id, result });
  } catch (err) {
    self.postMessage({ id, crash: String(err && err.message || err) });
  }
};
