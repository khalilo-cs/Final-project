//! واجهة WebAssembly بسيطة (C ABI) لمفسر ضاد، بلا أدوات توليد إضافية.
//!
//! بروتوكول الاستدعاء من JavaScript:
//! 1. `dhad_alloc(n)` لحجز n بايت ثم نسخ نص البرنامج (UTF-8) إليها.
//! 2. `dhad_run(ptr, n, fuel)` أو `dhad_check(ptr, n)` أو `dhad_explain(code)`.
//! 3. النتيجة نص JSON يُقرأ من `dhad_result_ptr()` بطول `dhad_result_len()`.
//! 4. `dhad_free(ptr, n)` لتحرير المدخل.
//!
//! تستورد الوحدة دالة واحدة من المضيف: `env.dhad_now_ms() -> f64` (ساعة المتصفح).

use dhad_diagnostics::{explain, lookup, render, Diagnostic};
use dhad_interp::Interp;
use std::cell::RefCell;
use std::io::Write;
use std::rc::Rc;

thread_local! {
    static RESULT: RefCell<Vec<u8>> = const { RefCell::new(Vec::new()) };
}

#[cfg(target_arch = "wasm32")]
mod host {
    #[link(wasm_import_module = "env")]
    extern "C" {
        pub fn dhad_now_ms() -> f64;
    }
    pub fn now() -> f64 {
        // SAFETY: دالة مستوردة من المضيف بلا معاملات ولا حالة مشتركة.
        unsafe { dhad_now_ms() }
    }
}

#[cfg(not(target_arch = "wasm32"))]
mod host {
    pub fn now() -> f64 {
        dhad_interp::interp::system_clock_ms()
    }
}

#[derive(Clone, Default)]
struct SharedBuf(Rc<RefCell<Vec<u8>>>);

impl Write for SharedBuf {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        self.0.borrow_mut().extend_from_slice(buf);
        Ok(buf.len())
    }
    fn flush(&mut self) -> std::io::Result<()> {
        Ok(())
    }
}

fn json_str(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// إزاحة UTF-16 (وحدة المواضع في محررات المتصفح) لإزاحة بايت.
fn utf16_offset(src: &str, byte: usize) -> usize {
    src[..byte.min(src.len())].encode_utf16().count()
}

fn diag_json(d: &Diagnostic, src: &str) -> String {
    let mut fields = vec![
        format!("\"code\":{}", d.code),
        format!("\"codeStr\":{}", json_str(&d.code_str())),
        format!(
            "\"severity\":{}",
            json_str(match d.severity {
                dhad_diagnostics::Severity::Error => "error",
                dhad_diagnostics::Severity::Warning => "warning",
            })
        ),
        format!("\"message\":{}", json_str(&d.message)),
        format!("\"rendered\":{}", json_str(&render(d, src, "البرنامج.ضاد"))),
    ];
    if let Some(h) = &d.help {
        fields.push(format!("\"help\":{}", json_str(h)));
    }
    if let Some(e) = lookup(d.code) {
        fields.push(format!("\"title\":{}", json_str(e.title)));
        fields.push(format!("\"explanation\":{}", json_str(e.explanation)));
    }
    if let Some(span) = d.span {
        let (line, col) = dhad_diagnostics::line_col(src, span.start);
        fields.push(format!("\"line\":{line},\"col\":{col}"));
        fields.push(format!(
            "\"from\":{},\"to\":{}",
            utf16_offset(src, span.start),
            utf16_offset(src, span.end)
        ));
    }
    format!("{{{}}}", fields.join(","))
}

fn set_result(s: String) -> usize {
    RESULT.with(|r| {
        let mut r = r.borrow_mut();
        *r = s.into_bytes();
        r.len()
    })
}

/// تشغيل برنامج وإرجاع JSON: {ok, output, steps, ms, error?}
pub fn run_json(src: &str, fuel: Option<u64>) -> String {
    let src = dhad_syntax::normalize_source(src);
    let buf = SharedBuf::default();
    let start = host::now();
    let result = |ok: bool, err: Option<String>, steps: u64, buf: &SharedBuf| {
        let output = String::from_utf8_lossy(&buf.0.borrow()).to_string();
        let mut s = format!(
            "{{\"ok\":{ok},\"output\":{},\"steps\":{steps},\"ms\":{:.3}",
            json_str(&output),
            host::now() - start
        );
        if let Some(e) = err {
            s.push_str(&format!(",\"error\":{e}"));
        }
        s.push('}');
        s
    };
    let program = match dhad_syntax::parse(&src) {
        Ok(p) => p,
        Err(e) => return result(false, Some(diag_json(&e, &src)), 0, &buf),
    };
    let mut it = Interp::new(Box::new(buf.clone()));
    it.set_clock(host::now);
    it.fuel = fuel;
    let r = it.run(&program);
    let r = match r {
        Ok(()) if it.has_tests() => {
            let (_, failed) = it.run_tests();
            if failed == 0 {
                Ok(())
            } else {
                Err(None)
            }
        }
        Ok(()) => Ok(()),
        Err(e) => Err(Some(e)),
    };
    match r {
        Ok(()) => result(true, None, it.steps(), &buf),
        Err(None) => result(false, None, it.steps(), &buf),
        Err(Some(e)) => result(false, Some(diag_json(&e, &src)), it.steps(), &buf),
    }
}

/// فحص ثابت (للتشخيص الفوري أثناء الكتابة): {ok, diagnostics: [...]}
/// `ok` خطأ إن وُجد خطأ واحد على الأقل؛ التحذيرات لا تؤثر فيه.
pub fn check_json(src: &str) -> String {
    let src = dhad_syntax::normalize_source(src);
    let analysis = dhad_analysis::analyze(&src);
    let ok = !analysis
        .diagnostics
        .iter()
        .any(|d| d.severity == dhad_diagnostics::Severity::Error);
    let items: Vec<String> = analysis
        .diagnostics
        .iter()
        .map(|d| diag_json(d, &src))
        .collect();
    format!("{{\"ok\":{ok},\"diagnostics\":[{}]}}", items.join(","))
}

/// # Safety
/// يجب أن يشير `ptr` إلى `len` بايت من نص UTF-8 صالح محجوز بـ `dhad_alloc`.
unsafe fn input<'a>(ptr: *const u8, len: usize) -> &'a str {
    // SAFETY: يضمنه المستدعي كما في توثيق الدالة.
    let bytes = unsafe { std::slice::from_raw_parts(ptr, len) };
    std::str::from_utf8(bytes).unwrap_or("")
}

#[no_mangle]
pub extern "C" fn dhad_alloc(len: usize) -> *mut u8 {
    let mut v = Vec::<u8>::with_capacity(len.max(1));
    let p = v.as_mut_ptr();
    std::mem::forget(v);
    p
}

/// # Safety
/// `ptr` و`len` يجب أن يكونا من استدعاء سابق لـ `dhad_alloc` بالطول نفسه.
#[no_mangle]
pub unsafe extern "C" fn dhad_free(ptr: *mut u8, len: usize) {
    // SAFETY: يضمنه المستدعي.
    drop(unsafe { Vec::from_raw_parts(ptr, 0, len.max(1)) });
}

/// # Safety
/// انظر [`input`]. `fuel = 0` يعني بلا حد.
#[no_mangle]
pub unsafe extern "C" fn dhad_run(ptr: *const u8, len: usize, fuel: f64) -> usize {
    let src = unsafe { input(ptr, len) };
    let fuel = if fuel > 0.0 { Some(fuel as u64) } else { None };
    set_result(run_json(src, fuel))
}

/// # Safety
/// انظر [`input`].
#[no_mangle]
pub unsafe extern "C" fn dhad_check(ptr: *const u8, len: usize) -> usize {
    let src = unsafe { input(ptr, len) };
    set_result(check_json(src))
}

/// ترجمة البرنامج إلى WebAssembly. النتيجة إما بايتات الوحدة (تبدأ بـ `\0asm`)
/// أو JSON يصف الخطأ.
///
/// # Safety
/// انظر [`input`].
#[no_mangle]
pub unsafe extern "C" fn dhad_compile(ptr: *const u8, len: usize) -> usize {
    let src = dhad_syntax::normalize_source(unsafe { input(ptr, len) });
    match dhad_wasmgen::compile(&src) {
        Ok(wasm) => RESULT.with(|r| {
            *r.borrow_mut() = wasm;
            r.borrow().len()
        }),
        Err(e) => set_result(format!(
            "{{\"ok\":false,\"error\":{}}}",
            diag_json(&e, &src)
        )),
    }
}

/// الصيغة النصية (WAT) للوحدة المترجمة، أو JSON بالخطأ.
///
/// # Safety
/// انظر [`input`].
#[no_mangle]
pub unsafe extern "C" fn dhad_compile_wat(ptr: *const u8, len: usize) -> usize {
    let src = dhad_syntax::normalize_source(unsafe { input(ptr, len) });
    match dhad_wasmgen::compile_full(&src) {
        Ok(out) => set_result(format!(
            "{{\"ok\":true,\"wat\":{},\"size\":{}}}",
            json_str(&out.wat),
            out.wasm.len()
        )),
        Err(e) => set_result(format!(
            "{{\"ok\":false,\"error\":{}}}",
            diag_json(&e, &src)
        )),
    }
}

#[no_mangle]
pub extern "C" fn dhad_explain(code: u32) -> usize {
    let s = match explain(code as u16) {
        Some(t) => format!("{{\"ok\":true,\"text\":{}}}", json_str(&t)),
        None => "{\"ok\":false}".to_string(),
    };
    set_result(s)
}

#[no_mangle]
pub extern "C" fn dhad_result_ptr() -> *const u8 {
    RESULT.with(|r| r.borrow().as_ptr())
}

#[no_mangle]
pub extern "C" fn dhad_result_len() -> usize {
    RESULT.with(|r| r.borrow().len())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn run_ok_and_error_json() {
        let ok = run_json("اطبع(\"مرحبا\")", None);
        assert!(ok.starts_with("{\"ok\":true,\"output\":\"مرحبا\\n\""));
        let err = run_json("اطبع(\"س\" + ١)", None);
        assert!(err.contains("\"code\":1003"));
        assert!(err.contains("\"from\":5"));
    }

    #[test]
    fn fuel_is_applied() {
        assert!(run_json("طالما صحيح { }", Some(100)).contains("\"code\":2005"));
    }

    #[test]
    fn check_reports_syntax_error() {
        assert!(check_json("دع = ").contains("\"ok\":false"));
        let w = check_json("دع س = ١");
        assert!(
            w.contains("\"ok\":true") && w.contains("\"code\":3001"),
            "{w}"
        );
    }
}
