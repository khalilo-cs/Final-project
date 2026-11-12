//! المفسر المرجعي للغة ضاد.
//!
//! مفسر يمشي على شجرة البرنامج مباشرة (Tree-walking). الأولوية هنا لوضوح
//! الدلالات ورسائل الخطأ، لا للأداء؛ مسار الأداء هو مولّد WebAssembly.

pub mod builtins;
pub mod env;
pub mod interp;
pub mod value;

pub use dhad_diagnostics::Diagnostic;
pub use env::Env;
pub use interp::Interp;
pub use value::Value;

use std::io::Write;

/// تشغيل نص مصدري كامل: تطبيع → تحليل → تنفيذ.
///
/// يعيد النص المطبَّع مع الخطأ (إن وُجد) حتى يمكن عرضه بموقعه الصحيح.
pub fn run_source(
    src: &str,
    out: Box<dyn Write>,
    fuel: Option<u64>,
) -> (String, Result<(), Diagnostic>) {
    let normalized = dhad_syntax::normalize_source(src);
    let program = match dhad_syntax::parse(&normalized) {
        Ok(p) => p,
        Err(e) => return (normalized, Err(e)),
    };
    let mut it = Interp::new(out);
    it.fuel = fuel;
    let r = it.run(&program);
    (normalized, r)
}
