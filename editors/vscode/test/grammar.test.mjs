// اختبار قواعد TextMate بالمحرك نفسه الذي يستخدمه VS Code (vscode-textmate + oniguruma).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const vsctm = require("vscode-textmate");
const oniguruma = require("vscode-oniguruma");

const wasm = readFileSync(require.resolve("vscode-oniguruma/release/onig.wasm")).buffer;
await oniguruma.loadWASM(wasm);
const registry = new vsctm.Registry({
  onigLib: Promise.resolve({ createOnigScanner: (p) => new oniguruma.OnigScanner(p), createOnigString: (s) => new oniguruma.OnigString(s) }),
  loadGrammar: async () => vsctm.parseRawGrammar(readFileSync(new URL("../syntaxes/dhad.tmLanguage.json", import.meta.url), "utf8"), "dhad.json"),
});
const grammar = await registry.loadGrammar("source.dhad");

function tokens(line) {
  const r = grammar.tokenizeLine(line, vsctm.INITIAL);
  return r.tokens.map((t) => [line.slice(t.startIndex, t.endIndex), t.scopes.at(-1)]);
}
function scopeOf(line, text) {
  const found = tokens(line).find(([t]) => t === text);
  assert.ok(found, `«${text}» غير موجود في ${JSON.stringify(tokens(line))}`);
  return found[1];
}

const cases = [
  ["دع العمر = ٢٥", "دع", "storage.type.dhad"],
  ["دع العمر = ٢٥", "٢٥", "constant.numeric.dhad"],
  ["دع العمر = ٢٥", "العمر", "variable.other.dhad"],
  ["دالة مربع(ن) {", "مربع", "entity.name.function.dhad"],
  ["إذا س > ٠ {", "إذا", "keyword.control.dhad"],
  ["} وإلا {", "وإلا", "keyword.control.dhad"],
  ["لكل ع في ١..١٠ {", "..", "keyword.operator.range.dhad"],
  ["اطبع(\"س = ${س}\")", "اطبع", "support.function.builtin.dhad"],
  ["اطبع(\"س = ${س}\")", "${", "punctuation.section.interpolation.begin.dhad"],
  ["دع ج = صحيح و ليس خطأ", "صحيح", "constant.language.boolean.dhad"],
  ["دع ج = صحيح و ليس خطأ", "و", "keyword.operator.logical.dhad"],
  ["دع ج = صحيح و ليس خطأ", "ليس", "keyword.operator.logical.dhad"],
  ["استورد رياضيات", "رياضيات", "support.class.module.dhad"],
  ["## يحسب المضروب", "## يحسب المضروب", "comment.line.documentation.dhad"],
  ["دع ط = ٣٫١٤", "٣٫١٤", "constant.numeric.dhad"],
  ["جمع(١، 2)", "جمع", "entity.name.function.call.dhad"],
  ["جمع(١، 2)", "،", "punctuation.separator.comma.dhad"],
];
for (const [line, text, scope] of cases) assert.equal(scopeOf(line, text), scope, `${line} :: ${text}`);

// «و» في أول كلمة (مثل «ولد») لا تُلوَّن ككلمة مفتاحية.
assert.equal(scopeOf("دع ولد = ١", "ولد"), "variable.other.dhad");
// «في» داخل كلمة (مثل «فيبوناتشي») لا تُلوَّن.
assert.equal(scopeOf("فيبوناتشي(٥)", "فيبوناتشي"), "entity.name.function.call.dhad");

// كل أمثلة المستودع تُرمَّز دون «invalid».
const examplesDir = new URL("../../../examples/", import.meta.url);
const { readdirSync } = await import("node:fs");
let lines = 0;
for (const f of readdirSync(examplesDir).filter((f) => f.endsWith(".ضاد"))) {
  let state = vsctm.INITIAL;
  for (const line of readFileSync(new URL(f, examplesDir), "utf8").split("\n")) {
    const r = grammar.tokenizeLine(line, state);
    state = r.ruleStack;
    assert.ok(r.tokens.every((t) => !t.scopes.some((s) => s.startsWith("invalid"))), f);
    lines++;
  }
}
console.log(`✔ قواعد TextMate: ${cases.length + 2} حالة + ${lines} سطرًا من الأمثلة`);
