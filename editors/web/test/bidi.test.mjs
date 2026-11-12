// اختبارات وحدة لطبقة العزل الاتجاهي (BiDi).
import assert from "node:assert/strict";
import { isolatedRanges, needsIsolation } from "../src/bidi.js";

const cases = [
  ["سطر عربي محض بلا أرقام غربية", "دع العمر = ٢٥", []],
  ["معرّف لاتيني في بداية السطر", "result = مجموع + ٥", [["result", "ltr"]]],
  ["رقم غربي وسط سياق عربي", "دع س = 25 + ٣", [["25", "ltr"]]],
  ["عدد عشري غربي كوحدة واحدة", "دع ط = 3.14", [["3.14", "ltr"]]],
  ["نص حرفي مختلط يُعزل تلقائيًا", 'اطبع("hello مرحبا")', [['"hello مرحبا"', "auto"]]],
  ["نص بعلامات تنصيص عربية", "اطبع(«abc»)", [["«abc»", "auto"]]],
  ["تعليق مختلط", "دع س = ١ # comment تعليق", [["# comment تعليق", "auto"]]],
  ["معرّفان لاتينيان وعملية", "total = price * 2", [["total", "ltr"], ["price", "ltr"], ["2", "ltr"]]],
  ["نص غير مغلق لا يكسر العزل", 'اطبع("abc', [['"abc', "auto"]]],
  ["علامة اقتباس مهربة داخل النص", 'اطبع("a\\"b")', [['"a\\"b"', "auto"]]],
  ["أقواس متداخلة مع أرقام غربية", "ف((1 + 2) * [3])", [["1", "ltr"], ["2", "ltr"], ["3", "ltr"]]],
  ["الأرقام داخل النص لا تُعزل مرتين", 'اطبع("2024")', [['"2024"', "auto"]]],
];

let passed = 0;
for (const [name, line, expected] of cases) {
  const got = isolatedRanges(line).map((r) => [line.slice(r.from, r.to), r.dir]);
  assert.deepEqual(got, expected, name);
  passed++;
}
assert.equal(isolatedRanges("abc", 10)[0].from, 10, "الإزاحة تُضاف");
assert.equal(needsIsolation("دع س = ٢"), false);
assert.equal(needsIsolation("x = ٢"), true);
console.log(`✔ BiDi: ${passed + 3} حالة ناجحة`);
