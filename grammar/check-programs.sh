#!/usr/bin/env bash
# يتحقق من تطابق قواعد Tree-sitter مع المحلل المرجعي على كل برامج المستودع:
# البرامج الصحيحة نحويًا تُحلَّل بلا ERROR، والبرامج ذات الأخطاء النحوية تُنتج ERROR.
set -u
cd "$(dirname "$0")"
ok=0; fail=0
# أخطاء نحوية يجب أن يرفضها Tree-sitter أيضًا. (0004 سياسة معرّفات يفرضها المحلل المرجعي فقط.)
syntax_errors=" خطأ_0001 خطأ_0002 خطأ_0003 خطأ_0005 "
for f in ../tests/corpus/*.ضاد ../examples/*.ضاد; do
  name=$(basename "$f" .ضاد)
  [ "$name" = "خطأ_0004" ] && continue
  out=$(npx --no tree-sitter parse --quiet "$f" 2>/dev/null)
  if [[ "$syntax_errors" == *" $name "* ]]; then
    if [ -n "$out" ]; then ok=$((ok+1)); else fail=$((fail+1)); echo "✘ كان يجب رفض $f"; fi
  else
    if [ -z "$out" ]; then ok=$((ok+1)); else fail=$((fail+1)); echo "✘ $f"; echo "$out"; fi
  fi
done
echo "Tree-sitter مقابل المحلل المرجعي: تطابق $ok — اختلاف $fail"
[ "$fail" -eq 0 ]
