//! خاصية على كل برامج المستودع: التنسيق ينجح، ولا يغيّر الرموز (يفرضه المنسّق نفسه)،
//! ومستقر (تنسيق الناتج لا يغيّره)، والبرنامج المنسَّق يُحلَّل نحويًا كالأصل.

use std::path::Path;

#[test]
fn every_program_formats_stably() {
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut checked = 0;
    for dir in [
        "examples",
        "tests/corpus",
        "benchmarks/programs",
        "benchmarks/conformance",
    ] {
        for entry in std::fs::read_dir(root.join(dir)).unwrap() {
            let path = entry.unwrap().path();
            if path.extension().is_none_or(|e| e != "ضاد") {
                continue;
            }
            let src = dhad_syntax::normalize_source(&std::fs::read_to_string(&path).unwrap());
            let Ok(once) = dhad_fmt::format(&src) else {
                // ملفات الأخطاء اللغوية المتعمدة لا تُنسَّق.
                assert!(dhad_syntax::tokenize(&src).is_err(), "{}", path.display());
                continue;
            };
            let twice = dhad_fmt::format(&once).unwrap();
            assert_eq!(once, twice, "غير مستقر: {}", path.display());
            assert_eq!(
                dhad_syntax::parse(&src).is_ok(),
                dhad_syntax::parse(&once).is_ok(),
                "تغيّرت صحة التحليل: {}",
                path.display()
            );
            checked += 1;
        }
    }
    assert!(checked >= 35, "{checked}");
}
