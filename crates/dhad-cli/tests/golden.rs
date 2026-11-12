//! اختبارات ذهبية (golden): كل برنامج في `tests/corpus/` و`examples/` له ملف
//! `.المتوقع` بجانبه يحتوي المخرجات الكاملة ورمز الخروج. أي اختلاف يُفشل الاختبار.
//!
//! لتحديث الملفات المتوقعة بعد تغيير مقصود: `DHAD_BLESS=1 cargo test -p dhad-cli`.

use std::path::{Path, PathBuf};
use std::process::Command;

fn root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn run_case(src: &Path) -> String {
    let name = src.file_name().unwrap().to_string_lossy().to_string();
    let cmd = if name.contains("اختبار") {
        "اختبر"
    } else {
        "شغّل"
    };
    let out = Command::new(env!("CARGO_BIN_EXE_dhad"))
        .arg(cmd)
        .arg(&name)
        .current_dir(src.parent().unwrap())
        .output()
        .expect("تعذّر تشغيل dhad");
    let mut s = String::from_utf8_lossy(&out.stdout).to_string();
    if !out.stderr.is_empty() {
        s.push_str("--- stderr ---\n");
        s.push_str(&String::from_utf8_lossy(&out.stderr));
    }
    s.push_str(&format!(
        "--- exit: {} ---\n",
        out.status.code().unwrap_or(-1)
    ));
    s
}

fn check_dir(dir: &str) -> usize {
    let bless = std::env::var("DHAD_BLESS").is_ok();
    let mut checked = 0;
    let mut failures = Vec::new();
    let mut entries: Vec<_> = std::fs::read_dir(root().join(dir))
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().is_some_and(|e| e == "ضاد"))
        .collect();
    entries.sort();
    for src in entries {
        let expected_path = src.with_extension("المتوقع");
        let actual = run_case(&src);
        if bless {
            std::fs::write(&expected_path, &actual).unwrap();
        }
        let Ok(expected) = std::fs::read_to_string(&expected_path) else {
            // برامج تفاعلية أو عشوائية بلا ملف متوقع: يكفي أن تُحلَّل بنجاح.
            let check = Command::new(env!("CARGO_BIN_EXE_dhad"))
                .arg("افحص")
                .arg(&src)
                .output()
                .unwrap();
            assert!(check.status.success(), "فشل فحص {}", src.display());
            continue;
        };
        checked += 1;
        if expected != actual {
            failures.push(format!(
                "✘ {}\n===== المتوقع =====\n{expected}===== الفعلي =====\n{actual}",
                src.display()
            ));
        }
    }
    assert!(failures.is_empty(), "\n{}", failures.join("\n"));
    checked
}

#[test]
fn corpus() {
    assert!(check_dir("tests/corpus") >= 25);
}

#[test]
fn examples() {
    assert!(check_dir("examples") >= 4);
}

#[test]
fn explain_command() {
    let out = Command::new(env!("CARGO_BIN_EXE_dhad"))
        .args(["شرح", "١٠٠٣"])
        .output()
        .unwrap();
    assert!(out.status.success());
    assert!(String::from_utf8_lossy(&out.stdout).contains("لا يمكن جمع نص مع عدد"));
}

#[test]
fn fuel_limit_stops_infinite_loop() {
    let dir = std::env::temp_dir().join("dhad-fuel-test");
    std::fs::create_dir_all(&dir).unwrap();
    let f = dir.join("حلقة.ضاد");
    std::fs::write(&f, "طالما صحيح { }\n").unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_dhad"))
        .args(["شغّل", "--وقود", "500"])
        .arg(&f)
        .output()
        .unwrap();
    assert_eq!(out.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&out.stderr).contains("ضاد-2005"));
}

#[test]
fn repl_session() {
    use std::io::Write;
    let mut child = Command::new(env!("CARGO_BIN_EXE_dhad"))
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .unwrap();
    child
        .stdin
        .take()
        .unwrap()
        .write_all("دع س = ٤\nدالة م(ن) {\n أرجع ن * ١٠\n}\nم(س)\nخروج\n".as_bytes())
        .unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(String::from_utf8_lossy(&out.stdout).contains("40"));
}
