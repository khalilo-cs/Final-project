#!/usr/bin/env python3
"""يشغّل كل كتلة ```dhad في التوثيق (المرجع، الـ README، المعمارية) ويتحقق أنها تعمل بلا أخطاء.

الكتل التي تبدأ بالتعليق «# خطأ متعمد» تُتوقع أن تفشل. الاستخدام: python3 tools/check_doc_examples.py
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "README.md", *sorted((ROOT / "docs" / "spec").glob("*.md")), ROOT / "docs" / "architecture.md"]
CLI = ROOT / "target" / "debug" / "dhad"

failures, count = [], 0
for doc in DOCS:
    if not doc.exists():
        continue
    for m in re.finditer(r"```dhad\n(.*?)```", doc.read_text(encoding="utf-8"), re.S):
        code = m.group(1)
        expect_error = code.lstrip().startswith("# خطأ متعمد")
        count += 1
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "مثال.ضاد"
            f.write_text(code, encoding="utf-8")
            r = subprocess.run([str(CLI), "شغّل", "--وقود", "1000000", str(f)], capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30)
        if (r.returncode != 0) != expect_error:
            line = doc.read_text(encoding="utf-8")[: m.start()].count("\n") + 1
            failures.append(f"{doc.relative_to(ROOT)}:{line}\n{code}\n{r.stderr}")

if failures:
    print("✘ أمثلة لا تعمل:\n\n" + "\n\n".join(failures))
    sys.exit(1)
print(f"✔ أمثلة التوثيق: {count} كتلة تعمل")
