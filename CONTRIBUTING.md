# المساهمة في ضاد

## التجهيز

```bash
rustup target add wasm32-unknown-unknown
cargo build                       # الأدوات: target/debug/dhad و dhad-lsp
(cd editors/web && npm ci && npm run build && npm run serve)   # الساحة على http://127.0.0.1:8080
```

## قبل أي دفعة

```bash
cargo fmt --all && cargo clippy --all-targets -- -D warnings && cargo test --all
cargo run -q -p dhad-cli -- نسّق --تحقق examples/*.ضاد tests/corpus/0*.ضاد benchmarks/*/*.ضاد
python3 tools/gen_error_docs.py --check && python3 tools/check_doc_examples.py
(cd grammar && npx tree-sitter test && ./check-programs.sh)
(cd editors/web && npm test)
node benchmarks/run.mjs --check
```

كلها تعمل في CI (`.github/workflows/ci.yml`).

## وصفات شائعة

| أريد أن… | الخطوات |
|---|---|
| **أضيف كلمة مفتاحية** | `Kw` في `crates/dhad-syntax/src/lexer.rs` ← المحلل النحوي ← المفسر ← `grammar/grammar.js` (والكلمات المحجوزة) ← `editors/web/src/lang.js` ← قواعد TextMate ← `dhad-analysis/catalog.rs` ← مرجع اللغة |
| **أضيف دالة مدمجة** | `crates/dhad-interp/src/builtins.rs` + وصفها في `crates/dhad-analysis/src/catalog.rs` (اختبار `catalog_matches_interpreter` يذكّرك) + الإكمال في `lang.js` |
| **أضيف كود خطأ** | `CATALOG` في `crates/dhad-diagnostics` ← مثال خاطئ في `tests/corpus/خطأ_XXXX.ضاد` ← مثال مصحح في `FIXES` في `tools/gen_error_docs.py` ← `python3 tools/gen_error_docs.py` |
| **أغيّر مخرجات مقصودًا** | `DHAD_BLESS=1 cargo test -p dhad-cli` يحدّث ملفات `.المتوقع`؛ راجع الفرق قبل الدفع |
| **أوسّع مولّد WASM** | `crates/dhad-wasmgen` + برنامج في `benchmarks/conformance/` يغطي البنية الجديدة؛ `node benchmarks/run.mjs --check` يجب أن يبقى متطابقًا |
| **أضيف درسًا** | `learn/lessons.mjs`؛ `node editors/web/test/lessons.test.mjs` يتحقق أن الحل ينجح والبداية تفشل |
| **أسجّل قرارًا معماريًا** | ملف جديد في `docs/adr/` على نمط الموجود |

## الأسلوب

- الأسماء في الكود بالإنجليزية، والتعليقات والرسائل والتوثيق بالعربية.
- كل رسالة للمستخدم تحمل كود خطأ موثّقًا؛ لا رسائل بلا كود.
- برامج ضاد في المستودع منسَّقة بـ `ضاد نسّق`.
