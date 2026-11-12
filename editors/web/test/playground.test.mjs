// اختبار شامل للساحة في متصفح حقيقي (Chromium عبر Playwright).
import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { createRequire } from "node:module";
import { execSync } from "node:child_process";

async function loadPlaywright() {
  try { return await import("playwright"); } catch {
    const globalRoot = execSync("npm root -g").toString().trim();
    return createRequire(globalRoot + "/")("playwright");
  }
}
const { chromium, devices } = await loadPlaywright();
import { serve } from "../serve.mjs";

const shots = new URL("../test-results/", import.meta.url).pathname;
mkdirSync(shots, { recursive: true });
const server = await serve(0);
const base = `http://127.0.0.1:${server.address().port}/`;
const browser = await chromium.launch();
const errors = [];

async function open(ctxOpts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 820 }, deviceScaleFactor: 1, ...ctxOpts });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && !/fonts\.g/.test(m.text()) && errors.push(m.text()));
  await page.goto(base);
  await page.waitForFunction(() => window.dhad && document.querySelector(".cm-content"));
  return { ctx, page };
}

async function setCode(page, code) {
  await page.evaluate((c) => window.dhad.view.dispatch({ changes: { from: 0, to: window.dhad.view.state.doc.length, insert: c } }), code);
}

async function runAndWait(page) {
  await page.click("#run");
  await page.waitForFunction(() => /✔|✘/.test(document.getElementById("status").textContent), null, { timeout: 15000 });
  return page.locator("#output").innerText();
}

const { ctx, page } = await open();

// ١) المثال الافتراضي
let out = await runAndWait(page);
assert.match(out, /مرحبًا يا عالم!/);

// ٢) الأعداد الأولية
await page.selectOption("#examples", "الأعداد_الأولية");
out = await runAndWait(page);
assert.match(out, /2 عدد أولي ومضروبه 2/);
assert.match(out, /7 عدد أولي ومضروبه 5040/);
await page.screenshot({ path: shots + "desktop-run.png" });

// ٣) الأرقام الشرقية
await page.check("#digits");
await page.waitForFunction(() => document.getElementById("output").innerText.includes("٥٠٤٠"));
await page.uncheck("#digits");
await page.waitForFunction(() => document.getElementById("output").innerText.includes("5040"));

// ٤) خطأ متعمد + التلميحات المتدرجة
await page.selectOption("#examples", "خطأ_متعمد");
out = await runAndWait(page);
assert.match(out, /ضاد-1003/);
assert.match(out, /لا يمكن جمع نص مع عدد/);
for (let i = 0; i < 3; i++) await page.click(".hint-btn");
assert.equal(await page.locator(".hint").count(), 3);
assert.equal(await page.locator(".hint-btn").count(), 0);
assert.match(await page.locator(".hints").innerText(), /نص\(العدد\)/);
await page.screenshot({ path: shots + "desktop-error-hints.png" });

// ٥) التشخيص الفوري أثناء الكتابة (بلا تشغيل)
await setCode(page, "دع س = (١ + \n");
await page.waitForSelector(".cm-lintRange-error, .cm-lint-marker-error", { timeout: 8000 });

// ٦) حلقة لا تنتهي: يجب أن تتوقف (بالوقود أو بالمهلة) وتبقى الصفحة مستجيبة
await setCode(page, "دع س = ٠\nطالما صحيح {\n    س = س + ١\n}\n");
out = await runAndWait(page);
assert.match(out, /ضاد-2005/);
await setCode(page, 'اطبع("ما زلت أعمل")');
out = await runAndWait(page);
assert.match(out, /ما زلت أعمل/);

// ٧) الإكمال التلقائي بالعربية
await setCode(page, "");
await page.click(".cm-content");
await page.keyboard.type("اطب");
await page.waitForSelector(".cm-tooltip-autocomplete");
assert.match(await page.locator(".cm-tooltip-autocomplete").innerText(), /اطبع/);
await page.keyboard.press("Escape");
await setCode(page, "استورد رياضيات\nرياضيات.");
await page.evaluate(() => { const v = window.dhad.view; v.dispatch({ selection: { anchor: v.state.doc.length } }); v.focus(); });
await page.keyboard.press("Control+Space");
await page.waitForSelector(".cm-tooltip-autocomplete");
assert.match(await page.locator(".cm-tooltip-autocomplete").innerText(), /جذر/);
await page.keyboard.press("Escape");

// ٧ب) التنسيق
await setCode(page, "دالة ف( أ ,ب ){\nأرجع أ+ب\n}");
await page.click("#format");
await page.waitForFunction(() => window.dhad.view.state.doc.toString().includes("أرجع أ + ب"));
assert.equal(await page.evaluate(() => window.dhad.view.state.doc.toString()), "دالة ف(أ، ب) {\n    أرجع أ + ب\n}\n");

// ٨) عزل BiDi مطبَّق فعلًا في DOM
await setCode(page, "دع result = مجموع + 25\nاطبع(\"hello مرحبا\")\n# total = price * 2 تعليق مختلط");
await page.waitForSelector(".bidi-ltr");
const iso = await page.evaluate(() => [...document.querySelectorAll(".bidi-ltr, .bidi-auto")].map((e) => [e.textContent, getComputedStyle(e).unicodeBidi, e.getAttribute("dir")]));
assert.deepEqual(iso.map((x) => x[0]), ["result", "25", '"hello مرحبا"', "# total = price * 2 تعليق مختلط"]);
assert.ok(iso.every((x) => x[1] === "isolate"));
await page.check("#show-bidi");
await page.locator(".editor-pane").screenshot({ path: shots + "desktop-bidi.png" });
await page.uncheck("#show-bidi");

// ٩) الترجمة إلى WebAssembly: المخرجات تطابق المفسر، وWAT يُعرض، والبنى غير المدعومة تُشرح
await page.selectOption("#examples", "مقارنة_الأداء");
const interpOut = await runAndWait(page);
await page.click("#compile");
await page.waitForFunction(() => document.querySelector("#status .badge"), null, { timeout: 15000 });
const compiledOut = await page.locator("#output").innerText();
assert.equal(compiledOut, interpOut, "مخرجات المترجم تطابق المفسر");
assert.match(compiledOut, /فيب\(٢٢\) = 17711/);
assert.match(await page.locator("#status").innerText(), /ترجمة .* تنفيذ .* بايت/);
await page.screenshot({ path: shots + "desktop-compiled.png" });
await page.click("#wat");
await page.waitForSelector(".wat pre");
const wat = await page.locator(".wat pre").innerText();
assert.match(wat, /\(module/);
assert.match(wat, /;; دالة فيب/);
await page.screenshot({ path: shots + "desktop-wat.png" });
await setCode(page, "دع ق = [١، ٢]\nاطبع(ق)");
await page.click("#compile");
await page.waitForFunction(() => /✘/.test(document.getElementById("status").textContent));
assert.match(await page.locator("#output").innerText(), /ضاد-4001/);
await setCode(page, "اطبع(٥ // ٠)");
await page.click("#compile");
await page.waitForFunction(() => document.querySelector("#status .badge"));
assert.match(await page.locator("#output").innerText(), /ضاد-2001/);

// ١٠) المشاركة: الرابط يعيد الكود نفسه
await setCode(page, "# برنامج مشترك\nاطبع(\"رابط ✔\")");
await page.click("#share");
await page.waitForSelector("#qr svg");
const url = await page.inputValue("#share-url");
await page.screenshot({ path: shots + "desktop-share.png" });
await page.click("#close-share");
const p2 = await ctx.newPage();
await p2.goto(url);
await p2.waitForFunction(() => window.dhad);
assert.equal(await p2.evaluate(() => window.dhad.view.state.doc.toString()), "# برنامج مشترك\nاطبع(\"رابط ✔\")");
await ctx.close();

// ١١) الدروس: تصحيح آلي، تقدم محفوظ، فتح الحل بعد محاولتين، رابط مباشر
const lessons = await open();
const lp = lessons.page;
await lp.click("#lessons-btn");
await lp.waitForSelector("#lesson-check");
assert.match(await lp.locator(".lesson h2").innerText(), /مرحبًا يا عالم/);
await lp.click("#lesson-check");
await lp.waitForSelector(".verdict.fail");
await lp.click("#lesson-check");
await lp.waitForSelector(".verdict.fail");
assert.equal(await lp.locator(".lesson-actions button", { hasText: "أظهر الحل" }).isEnabled(), true, "الحل يُتاح بعد محاولتين");
await lp.locator(".lesson-actions button", { hasText: "أظهر الحل" }).click();
await lp.click("#lesson-check");
await lp.waitForSelector(".verdict.pass");
assert.equal(await lp.locator(".dot.done").count(), 1);
await lp.locator(".lesson-nav button", { hasText: "التالي" }).click();
await lp.waitForFunction(() => document.querySelector(".lesson h2").textContent.includes("المتغيرات"));
await lp.evaluate(() => window.dhad.view.dispatch({ changes: { from: 0, to: window.dhad.view.state.doc.length, insert: window.dhad.LESSONS[1].solution } }));
await lp.click("#lesson-check");
await lp.waitForSelector(".verdict.pass");
await lp.screenshot({ path: shots + "desktop-lesson.png" });
await lp.goto(base + "?lesson=07");
await lp.waitForSelector("#lesson-check");
assert.match(await lp.locator(".lesson h2").innerText(), /الأخطاء صديقتك/);
assert.equal(await lp.locator(".dot.done").count(), 2, "التقدم محفوظ بعد إعادة التحميل");
await lp.click("#lesson-check");
await lp.waitForSelector(".verdict.fail");
assert.match(await lp.locator("#output").innerText(), /ضاد-1001/);
await lp.screenshot({ path: shots + "desktop-lesson-error.png" });
await lessons.ctx.close();

// ١٢) الهاتف + الوضع الليلي
const phone = await open({ ...devices["iPhone 13"], colorScheme: "dark" });
await phone.page.selectOption("#examples", "القوائم_والقواميس");
out = await runAndWait(phone.page);
assert.match(out, /مرتبة/);
const overflow = await phone.page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
assert.equal(overflow, false, "لا تمرير أفقي على الهاتف");
await phone.page.screenshot({ path: shots + "phone-dark.png" });
await phone.ctx.close();

await browser.close();
server.close();
assert.deepEqual(errors, [], "أخطاء في وحدة التحكم");
console.log("✔ الساحة: جميع سيناريوهات المتصفح ناجحة — اللقطات في", shots);
