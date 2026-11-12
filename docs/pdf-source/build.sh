#!/usr/bin/env bash
# يولّد docs/منصة-ضاد-وثيقة-المشروع-الشاملة.pdf من index.html.
# يحتاج: Node + Playwright (Chromium)، pdftotext (poppler-utils)، Python + pypdf، وخطوط Cairo وAmiri وNoto Sans/Kufi Arabic.
set -euo pipefail
cd "$(dirname "$0")"
node render.js out.pdf
python3 - <<'PY'
from pypdf import PdfReader, PdfWriter
foot, nof = PdfReader("out.pdf"), PdfReader("out-nofooter.pdf")
w = PdfWriter()
w.add_page(nof.pages[0])               # الغلاف بلا تذييل
for page in foot.pages[1:]:
    w.add_page(page)
w.add_metadata({"/Title": "منصة ضاد — وثيقة مشروع التخرج الشاملة",
                "/Subject": "منصة برمجة عربية متكاملة: لغة، مترجم متعدد الأهداف، وأدوات تطوير"})
w.write("../منصة-ضاد-وثيقة-المشروع-الشاملة.pdf")
print("pages:", len(w.pages))
PY
rm -f out.pdf out-nofooter.pdf
