const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');
const { execFileSync } = require('child_process');

const dir = __dirname;
const out = process.argv[2] || path.join(dir, 'out.pdf');
const footer = `<div style="width:100%;font-family:'Cairo','Noto Sans Arabic',sans-serif;font-size:8.5px;color:#5b6478;padding:0 16mm;display:flex;justify-content:space-between;direction:rtl">
    <span>منصة ضاد — وثيقة مشروع التخرج الشاملة</span>
    <span>صفحة <span class="pageNumber"></span> من <span class="totalPages"></span></span>
  </div>`;
const pdfOpts = (p) => ({
  path: p, format: 'A4', printBackground: true, preferCSSPageSize: true,
  displayHeaderFooter: true, headerTemplate: '<div></div>', footerTemplate: footer,
  margin: { top: '18mm', right: '16mm', bottom: '20mm', left: '16mm' },
});

function pageMap(pdf) {
  const info = execFileSync('pdfinfo', [pdf]).toString();
  const n = parseInt(/Pages:\s+(\d+)/.exec(info)[1], 10);
  const map = {};
  for (let i = 1; i <= n; i++) {
    const txt = execFileSync('pdftotext', ['-f', String(i), '-l', String(i), pdf, '-']).toString();
    const clean = txt.replace(/[\u200e\u200f\u202a-\u202e\u2066-\u2069\s]/g, ""); for (const m of clean.matchAll(/QQ(S[0-9A-Z]+)QQ/g)) if (!map[m[1]]) map[m[1]] = i;
  }
  return { n, map };
}

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('file://' + path.join(dir, 'index.html'), { waitUntil: 'networkidle' });
  await page.evaluate(() => document.fonts.ready);
  const tmp = path.join(dir, 'pass1.pdf');
  await page.pdf(pdfOpts(tmp));
  const { n, map } = pageMap(tmp);
  console.log('pass1 pages:', n, 'sections found:', Object.keys(map).length);
  await page.evaluate((map) => {
    document.querySelectorAll('[data-sec]').forEach(el => { const p = map[el.dataset.sec]; if (p) el.textContent = String(p); });
  }, map);
  await page.pdf(pdfOpts(out));
  const nf = pdfOpts(out.replace(/\.pdf$/, '-nofooter.pdf')); nf.displayHeaderFooter = false; await page.pdf(nf);
  const check = pageMap(out);
  const same = JSON.stringify(check.map) === JSON.stringify(map);
  console.log('pass2 pages:', check.n, 'stable:', same);
  fs.unlinkSync(tmp);
  await browser.close();
})();
