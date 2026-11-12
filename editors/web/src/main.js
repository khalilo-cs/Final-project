import { EditorView, basicSetup } from "codemirror";
import { EditorState, Compartment, RangeSetBuilder } from "@codemirror/state";
import { Decoration, ViewPlugin, Direction, keymap } from "@codemirror/view";
import { autocompletion } from "@codemirror/autocomplete";
import { linter, lintGutter, setDiagnostics } from "@codemirror/lint";
import { indentWithTab } from "@codemirror/commands";
import { indentUnit } from "@codemirror/language";
import qrcode from "qrcode-generator";
import { dhadLanguage, dhadHighlight, KEYWORDS, BUILTINS, MODULES } from "./lang.js";
import { isolatedRanges, needsIsolation } from "./bidi.js";
import EXAMPLES from "./examples.json";
import { LESSONS, gradedSource, judge } from "../../../learn/lessons.mjs";

const WASM_URL = new URL("dhad.wasm", document.baseURI).href;
const RUN_TIMEOUT_MS = 5000;
const FUEL = 20_000_000;

// ---------------- العامل المعزول ----------------
let worker = null;
let seq = 0;
const pending = new Map();

function spawnWorker() {
  worker = new Worker(new URL("worker.js", document.baseURI).href);
  worker.onmessage = (e) => {
    const p = pending.get(e.data.id);
    if (!p) return;
    pending.delete(e.data.id);
    clearTimeout(p.timer);
    e.data.crash ? p.reject(new Error(e.data.crash)) : p.resolve(e.data.result);
  };
}
spawnWorker();

function ask(msg, timeout = RUN_TIMEOUT_MS) {
  const id = ++seq;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      // الحلقة اللانهائية لا تُقاطَع من الداخل: نُنهي العامل ونبدأ غيره.
      pending.delete(id);
      worker.terminate();
      for (const [, p] of pending) { clearTimeout(p.timer); p.reject(new Error("restart")); }
      pending.clear();
      spawnWorker();
      reject(new Error("timeout"));
    }, timeout);
    pending.set(id, { resolve, reject, timer });
    worker.postMessage({ ...msg, id, wasmUrl: WASM_URL });
  });
}

// ---------------- BiDi ----------------
const ltrMark = Decoration.mark({ class: "bidi-ltr", bidiIsolate: Direction.LTR });
const autoMark = Decoration.mark({ class: "bidi-auto", attributes: { dir: "auto" }, bidiIsolate: null });

function buildIsolation(view) {
  const b = new RangeSetBuilder();
  for (const { from, to } of view.visibleRanges) {
    for (let pos = from; pos <= to;) {
      const line = view.state.doc.lineAt(pos);
      if (needsIsolation(line.text)) {
        for (const r of isolatedRanges(line.text, line.from)) {
          b.add(r.from, r.to, r.dir === "ltr" ? ltrMark : autoMark);
        }
      }
      pos = line.to + 1;
    }
  }
  return b.finish();
}

const bidiPlugin = ViewPlugin.fromClass(class {
  constructor(view) { this.decorations = buildIsolation(view); }
  update(u) { if (u.docChanged || u.viewportChanged) this.decorations = buildIsolation(u.view); }
}, {
  decorations: (v) => v.decorations,
  provide: (plugin) => EditorView.bidiIsolatedRanges.of((view) => view.plugin(plugin)?.decorations ?? Decoration.none),
});

// ---------------- الإكمال التلقائي ----------------
function completions(ctx) {
  const member = ctx.matchBefore(/[\p{L}_][\p{L}\p{N}\p{M}_]*\.[\p{L}\p{N}\p{M}_]*$/u);
  if (member) {
    const [mod] = member.text.split(".");
    const names = MODULES[mod];
    if (!names) return null;
    return {
      from: member.from + mod.length + 1,
      options: names.map((n) => ({ label: n, type: "function", detail: `من وحدة ${mod}` })),
      validFor: /^[\p{L}\p{N}\p{M}_]*$/u,
    };
  }
  const word = ctx.matchBefore(/[\p{L}_][\p{L}\p{N}\p{M}_]*/u);
  if (!word || (word.from === word.to && !ctx.explicit)) return null;
  const seen = new Set();
  const options = [];
  for (const [k, info] of KEYWORDS) { seen.add(k); options.push({ label: k, type: "keyword", info, boost: 2 }); }
  for (const [b, sig, info] of BUILTINS) { seen.add(b); options.push({ label: b, type: "function", detail: sig, info, boost: 1 }); }
  for (const m of Object.keys(MODULES)) { seen.add(m); options.push({ label: m, type: "namespace", detail: "وحدة" }); }
  const text = ctx.state.doc.toString();
  for (const m of text.matchAll(/(?:دع|ثابت|دالة|لكل)\s+([\p{L}_][\p{L}\p{N}\p{M}_]*[؟?]?)/gu)) {
    if (!seen.has(m[1]) && m[1] !== word.text) { seen.add(m[1]); options.push({ label: m[1], type: "variable", detail: "معرَّف في البرنامج" }); }
  }
  return { from: word.from, options, validFor: /^[\p{L}\p{N}\p{M}_]*$/u };
}

// ---------------- التشخيص الفوري ----------------
let lastError = null;
const liveLinter = linter(async (view) => {
  let res;
  try { res = await ask({ kind: "check", src: view.state.doc.toString() }, 2000); } catch { return []; }
  const len = view.state.doc.length;
  return (res.diagnostics || []).map((e) => {
    const from = Math.min(e.from ?? 0, len);
    return {
      from, to: Math.max(from, Math.min(e.to ?? from, len)),
      severity: e.severity === "warning" ? "warning" : "error",
      message: `${e.codeStr}: ${e.message}${e.help ? "\nمساعدة: " + e.help : ""}`,
    };
  });
}, { delay: 350 });

// ---------------- المحرر ----------------
const dirCompartment = new Compartment();
const params = new URLSearchParams(location.search);

async function decodeShared(hash) {
  try {
    const bytes = Uint8Array.from(atob(hash.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
    if ("DecompressionStream" in window) {
      const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
      return await new Response(stream).text();
    }
  } catch { /* رابط تالف: نتجاهله */ }
  return null;
}

async function encodeShared(text) {
  const stream = new Blob([text]).stream().pipeThrough(new CompressionStream("deflate-raw"));
  const bytes = new Uint8Array(await new Response(stream).arrayBuffer());
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function loadPref(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
function savePref(key, value) {
  try { localStorage.setItem(key, value); } catch { /* التخزين غير متاح */ }
}

let initial = EXAMPLES[0].code;
if (location.hash.length > 1) initial = (await decodeShared(location.hash.slice(1))) ?? initial;
else if (params.get("example")) initial = EXAMPLES.find((x) => x.id === params.get("example"))?.code ?? initial;
else initial = loadPref("dhad.draft", initial);

const view = new EditorView({
  parent: document.getElementById("editor"),
  state: EditorState.create({
    doc: initial,
    extensions: [
      basicSetup,
      keymap.of([
        indentWithTab,
        { key: "Mod-Enter", run: () => { run(); return true; } },
        { key: "Mod-Shift-Enter", run: () => { compileAndRun(); return true; } },
      ]),
      indentUnit.of("    "),
      dhadLanguage,
      dhadHighlight,
      bidiPlugin,
      dirCompartment.of(EditorView.contentAttributes.of({ dir: "rtl" })),
      autocompletion({ override: [completions], activateOnTyping: true }),
      liveLinter,
      lintGutter(),
      EditorView.updateListener.of((u) => { if (u.docChanged) savePref("dhad.draft", u.state.doc.toString()); }),
      EditorView.lineWrapping,
      EditorView.theme({ "&": { height: "100%" } }),
    ],
  }),
});

// ---------------- المخرجات ----------------
const $ = (id) => document.getElementById(id);
const out = $("output");
const status = $("status");
let easternDigits = loadPref("dhad.eastern", "0") === "1";
$("digits").checked = easternDigits;

const toEastern = (s) => s.replace(/[0-9]/g, (d) => "٠١٢٣٤٥٦٧٨٩"[d]);
const fmt = (s) => (easternDigits ? toEastern(s) : s);

function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text != null) n.textContent = text;
  return n;
}

function renderError(e) {
  lastError = e;
  const box = el("div", "err");
  const head = el("div", "err-head");
  head.append(el("span", "err-code", e.codeStr), el("span", "err-msg", e.message));
  box.append(head);
  if (e.line) box.append(el("div", "err-loc", fmt(`السطر ${e.line}، العمود ${e.col}`)));

  // التلميحات المتدرجة: كل مستوى يُكشف بطلب الطالب (سقالات تعليمية).
  const levels = [
    ["ماذا يعني الخطأ؟", e.explanation || e.title || e.message],
    ["أين المشكلة؟", e.line ? `انظر السطر ${e.line} — الجزء المظلَّل في المحرر هو موضع الخطأ.` : "راجع آخر سطر عدّلته."],
    ["كيف أصلحه؟", e.help || "راجع صياغة السطر مقارنةً بالأمثلة."],
  ];
  const hints = el("div", "hints");
  let shown = 0;
  const btn = el("button", "hint-btn", `تلميح ١ من ${levels.length}: ${levels[0][0]}`);
  btn.type = "button";
  btn.onclick = () => {
    const [title, body] = levels[shown];
    const h = el("div", "hint");
    h.append(el("b", null, title), el("p", null, body));
    hints.append(h);
    shown++;
    if (shown >= levels.length) btn.remove();
    else btn.textContent = `تلميح ${toEastern(String(shown + 1))} من ${toEastern(String(levels.length))}: ${levels[shown][0]}`;
  };
  box.append(hints, btn);
  if (e.from != null) {
    view.dispatch({ selection: { anchor: Math.min(e.from, view.state.doc.length) }, scrollIntoView: true });
    view.dispatch(setDiagnostics(view.state, [{
      from: Math.min(e.from, view.state.doc.length),
      to: Math.min(Math.max(e.to, e.from), view.state.doc.length),
      severity: "error", message: `${e.codeStr}: ${e.message}`,
    }]));
  }
  return box;
}

async function run() {
  out.replaceChildren();
  status.textContent = "جارٍ التشغيل…";
  status.className = "status running";
  setBusy(true);
  try {
    const res = await ask({ kind: "run", src: view.state.doc.toString(), fuel: FUEL });
    if (res.output) out.append(el("pre", "stdout", fmt(res.output)));
    if (res.error) out.append(renderError(res.error));
    else lastError = null;
    if (!res.output && !res.error) out.append(el("div", "muted", "انتهى البرنامج دون مخرجات."));
    status.textContent = fmt(`${res.ok ? "✔ اكتمل" : "✘ توقف بخطأ"} — ${res.steps.toLocaleString("en")} خطوة في ${res.ms.toFixed(1)} ملّي ثانية`);
    status.className = "status " + (res.ok ? "ok" : "bad");
  } catch (err) {
    if (err.message === "timeout") {
      out.append(renderError({
        codeStr: "ضاد-2005", code: 2005, message: `تجاوز البرنامج المهلة الزمنية (${RUN_TIMEOUT_MS / 1000} ثوانٍ) فأُوقف`,
        explanation: "استغرق البرنامج وقتًا أطول من المسموح به في الساحة، وغالبًا السبب حلقة لا ينتهي شرطها.",
        help: "تحقق من أن شرط حلقة «طالما» يصبح خطأً في النهاية، وأن المتغير داخلها يتغير.",
      }));
      status.textContent = "✘ أُوقف لتجاوز المهلة";
      status.className = "status bad";
    } else {
      out.append(el("div", "err", "تعذّر تشغيل المفسر: " + err.message));
      status.textContent = "✘ خطأ داخلي";
      status.className = "status bad";
    }
  } finally {
    setBusy(false);
  }
}

// ---------------- مسار WebAssembly ----------------
function setBusy(busy) {
  for (const id of ["run", "compile", "wat"]) $(id).disabled = busy;
}

async function errorFromCode(code, message) {
  let info = {};
  try { info = await ask({ kind: "explain", code }); } catch { /* الشرح اختياري */ }
  const lines = (info.text || "").split("\n").filter(Boolean);
  return {
    codeStr: `ضاد-${code}`, code, message: message || lines[0]?.replace(/^ضاد-\d+:\s*/, "") || "خطأ وقت التشغيل",
    explanation: lines[1], help: lines.find((l) => l.startsWith("مساعدة:"))?.replace("مساعدة: ", ""),
  };
}

async function compileAndRun() {
  out.replaceChildren();
  status.textContent = "جارٍ الترجمة إلى WebAssembly…";
  status.className = "status running";
  setBusy(true);
  try {
    const res = await ask({ kind: "compile-run", src: view.state.doc.toString() });
    if (res.error) {
      out.append(renderError(res.error));
      status.textContent = "✘ تعذّرت الترجمة — جرّب «▶ تشغيل» بالمفسر";
      status.className = "status bad";
      return;
    }
    if (res.output) out.append(el("pre", "stdout", fmt(res.output)));
    if (res.failCode) out.append(renderError(await errorFromCode(res.failCode)));
    if (res.trap) {
      const deep = /call stack|recursion/i.test(res.trap);
      out.append(renderError(deep
        ? await errorFromCode(2004, "تجاوز عمق الاستدعاء في الوحدة المترجمة")
        : { codeStr: "WASM", message: res.trap }));
    }
    const head = el("span", "badge", "⚡ WebAssembly");
    status.replaceChildren(head, document.createTextNode(fmt(
      `${res.ok ? "✔" : "✘"} ترجمة ${res.compileMs.toFixed(1)} ملّي ثانية، تنفيذ ${res.runMs.toFixed(2)} ملّي ثانية، ${res.size} بايت`)));
    status.className = "status " + (res.ok ? "ok" : "bad");
  } catch (err) {
    if (err.message === "timeout") {
      out.append(renderError(await errorFromCode(2005, `تجاوز البرنامج المترجم المهلة (${RUN_TIMEOUT_MS / 1000} ثوانٍ) فأُوقف`)));
      status.textContent = "✘ أُوقف لتجاوز المهلة";
    } else {
      out.append(el("div", "err", "تعذّر التشغيل: " + err.message));
      status.textContent = "✘ خطأ داخلي";
    }
    status.className = "status bad";
  } finally {
    setBusy(false);
  }
}

async function showWat() {
  setBusy(true);
  try {
    const res = await ask({ kind: "wat", src: view.state.doc.toString() });
    out.replaceChildren();
    if (!res.ok) {
      out.append(renderError(res.error));
      status.textContent = "✘ تعذّرت الترجمة";
      status.className = "status bad";
      return;
    }
    const d = el("details", "wat");
    d.open = true;
    d.append(el("summary", null, `الصيغة النصية لوحدة WebAssembly (${res.size} بايت)`), el("pre", null, res.wat));
    out.append(d);
    status.textContent = "هذه هي التعليمات التي ينفّذها المتصفح فعلًا.";
    status.className = "status";
  } finally {
    setBusy(false);
  }
}

// ---------------- أدوات الشريط ----------------
$("run").onclick = run;
$("compile").onclick = compileAndRun;
$("wat").onclick = showWat;

const sel = $("examples");
for (const ex of EXAMPLES) sel.append(Object.assign(document.createElement("option"), { value: ex.id, textContent: ex.title }));
sel.onchange = () => {
  if (lessonIndex >= 0) closeLessons();
  const ex = EXAMPLES.find((x) => x.id === sel.value);
  if (ex) view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: ex.code } });
  out.replaceChildren(el("div", "muted", "اضغط «تشغيل» أو Ctrl+Enter."));
  status.textContent = ""; status.className = "status";
};

$("dir").onclick = () => {
  const rtl = view.contentDOM.getAttribute("dir") !== "ltr";
  view.dispatch({ effects: dirCompartment.reconfigure(EditorView.contentAttributes.of({ dir: rtl ? "ltr" : "rtl" })) });
  $("dir").textContent = rtl ? "اتجاه: يسار ← يمين" : "اتجاه: يمين ← يسار";
};

$("digits").onchange = (e) => {
  easternDigits = e.target.checked;
  savePref("dhad.eastern", easternDigits ? "1" : "0");
  if (out.childElementCount) run();
};

$("show-bidi").onchange = (e) => document.body.classList.toggle("show-bidi", e.target.checked);

const dialog = $("share-dialog");
$("share").onclick = async () => {
  const hash = await encodeShared(view.state.doc.toString());
  const url = `${location.origin}${location.pathname}#${hash}`;
  history.replaceState(null, "", "#" + hash);
  $("share-url").value = url;
  const qr = qrcode(0, "M");
  qr.addData(url);
  qr.make();
  // SVG مولَّد من مصفوفة الرمز فقط (بلا title/alt)، فلا يدخل فيه أي نص من المستخدم.
  $("qr").innerHTML = qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  dialog.showModal();
};
$("copy").onclick = async () => {
  try { await navigator.clipboard.writeText($("share-url").value); $("copy").textContent = "نُسخ ✔"; }
  catch { $("share-url").select(); }
  setTimeout(() => ($("copy").textContent = "نسخ الرابط"), 1500);
};
$("close-share").onclick = () => dialog.close();

// ---------------- الدروس ----------------
const lessonBox = $("lesson");
let lessonIndex = -1;
let failedChecks = 0;

function loadJson(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function saveJson(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* التخزين غير متاح */ }
}
let progress = new Set(loadJson("dhad.lessons.done", []));

/** عرض نص الدرس: فقرات، و`كود` داخلي، و**عريض**، وكتل ```dhad — كلها عبر textContent. */
function renderBody(parts) {
  const frag = document.createDocumentFragment();
  for (const part of parts) {
    const block = part.match(/^```dhad\n([\s\S]*?)```$/);
    if (block) { frag.append(el("pre", null, block[1].replace(/\n$/, ""))); continue; }
    const p = el("p");
    for (const tok of part.split(/(`[^`]+`|\*\*[^*]+\*\*)/)) {
      if (!tok) continue;
      if (tok.startsWith("`")) p.append(el("code", null, tok.slice(1, -1)));
      else if (tok.startsWith("**")) p.append(el("strong", null, tok.slice(2, -2)));
      else p.append(document.createTextNode(tok));
    }
    frag.append(p);
  }
  return frag;
}

function setDoc(code) {
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: code } });
}

function openLesson(i, { restoreDraft = true } = {}) {
  lessonIndex = Math.max(0, Math.min(LESSONS.length - 1, i));
  failedChecks = 0;
  const L = LESSONS[lessonIndex];
  saveJson("dhad.lessons.current", L.id);
  history.replaceState(null, "", `?lesson=${L.id}`);
  const drafts = loadJson("dhad.lessons.drafts", {});
  setDoc(restoreDraft && drafts[L.id] ? drafts[L.id] : L.starter);

  const top = el("div", "lesson-top");
  top.append(el("h2", null, `الدرس ${toEastern(String(lessonIndex + 1))}: ${L.title}`));
  const nav = el("div", "lesson-nav");
  const prev = el("button", null, "→ السابق"); prev.type = "button"; prev.disabled = lessonIndex === 0;
  const next = el("button", null, "التالي ←"); next.type = "button"; next.disabled = lessonIndex === LESSONS.length - 1;
  prev.onclick = () => openLesson(lessonIndex - 1);
  next.onclick = () => openLesson(lessonIndex + 1);
  const dots = el("div", "dots");
  LESSONS.forEach((x, k) => {
    const d = el("button", "dot" + (progress.has(x.id) ? " done" : "") + (k === lessonIndex ? " current" : ""));
    d.type = "button";
    d.title = `${x.title}${progress.has(x.id) ? " ✔" : ""}`;
    d.setAttribute("aria-label", d.title);
    d.onclick = () => openLesson(k);
    dots.append(d);
  });
  nav.append(prev, dots, next);
  top.append(nav);

  const actions = el("div", "lesson-actions");
  const check = el("button", "primary", "تحقق من حلّي ✔"); check.type = "button"; check.id = "lesson-check";
  const hint = el("button", null, "💡 تلميح"); hint.type = "button";
  const sol = el("button", null, "أظهر الحل"); sol.type = "button"; sol.disabled = true; sol.title = "يُتاح بعد محاولتين";
  const reset = el("button", null, "↺ ابدأ من جديد"); reset.type = "button";
  const verdict = el("div");
  check.onclick = () => checkLesson(verdict, sol);
  hint.onclick = () => { verdict.className = "verdict"; verdict.replaceChildren(el("p", null, "💡 " + L.hint)); };
  sol.onclick = () => setDoc(L.solution);
  reset.onclick = () => setDoc(L.starter);
  actions.append(check, hint, sol, reset);

  lessonBox.replaceChildren(top, el("div", "lesson-concept", L.concept), renderBody(L.body), actions, verdict);
  lessonBox.hidden = false;
  $("lessons-btn").setAttribute("aria-pressed", "true");
  out.replaceChildren(el("div", "muted", "اكتب حلك في المحرر ثم اضغط «تحقق من حلّي»."));
  status.textContent = ""; status.className = "status";
}

async function checkLesson(verdict, solBtn) {
  const L = LESSONS[lessonIndex];
  verdict.className = "verdict"; verdict.replaceChildren(el("p", null, "جارٍ التصحيح…"));
  let res;
  try {
    res = await ask({ kind: "run", src: gradedSource(L, view.state.doc.toString()), fuel: FUEL });
  } catch (err) {
    res = { ok: false, output: "", error: { codeStr: "ضاد-2005", code: 2005, message: "تجاوز البرنامج المهلة — ربما حلقة لا تنتهي" } };
  }
  const v = judge(L, res);
  out.replaceChildren();
  if (res.output) out.append(el("pre", "stdout", fmt(res.output)));
  if (res.error) out.append(renderError(res.error));
  if (v.passed) {
    progress.add(L.id);
    saveJson("dhad.lessons.done", [...progress]);
    verdict.className = "verdict pass";
    const done = progress.size === LESSONS.length;
    verdict.replaceChildren(el("p", null, done ? "🎉 أحسنت! أنهيت كل الدروس." : "✔ أحسنت! حلّك صحيح."));
    lessonBox.querySelectorAll(".dot")[lessonIndex].classList.add("done");
    return;
  }
  failedChecks++;
  if (failedChecks >= 2) { solBtn.disabled = false; solBtn.title = ""; }
  verdict.className = "verdict fail";
  if (v.reason === "output") {
    verdict.replaceChildren(el("p", null, "✘ المخرجات لا تطابق المطلوب. المتوقع:"), el("pre", null, fmt(v.want)));
  } else if (v.reason === "tests") {
    verdict.replaceChildren(el("p", null, "✘ بعض الاختبارات لم تنجح — انظر العلامات ✘ في المخرجات."));
  } else {
    verdict.replaceChildren(el("p", null, "✘ في البرنامج خطأ — اقرأ الرسالة والتلميحات في المخرجات."));
  }
}

function closeLessons() {
  lessonIndex = -1;
  lessonBox.hidden = true;
  $("lessons-btn").setAttribute("aria-pressed", "false");
  history.replaceState(null, "", location.pathname);
}

$("lessons-btn").onclick = () => {
  if (lessonIndex >= 0) { closeLessons(); return; }
  const cur = loadJson("dhad.lessons.current", LESSONS[0].id);
  openLesson(Math.max(0, LESSONS.findIndex((x) => x.id === cur)));
};

view.dom.addEventListener("input", () => {
  if (lessonIndex < 0) return;
  const drafts = loadJson("dhad.lessons.drafts", {});
  drafts[LESSONS[lessonIndex].id] = view.state.doc.toString();
  saveJson("dhad.lessons.drafts", drafts);
});

out.append(el("div", "muted", "اضغط «تشغيل» أو Ctrl+Enter لتنفيذ البرنامج."));
if (params.get("lesson")) {
  const i = LESSONS.findIndex((x) => x.id === params.get("lesson"));
  if (i >= 0) openLesson(i);
}
window.dhad = { view, run, compileAndRun, showWat, ask, openLesson, LESSONS };
