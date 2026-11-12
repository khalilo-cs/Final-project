//! الأمر «ضاد» (dhad).
//!
//! ```text
//! dhad شغّل <ملف.ضاد>      تشغيل برنامج
//! dhad افحص <ملف.ضاد>      فحص نحوي فقط
//! dhad اختبر <ملف.ضاد>     تشغيل كتل «اختبر»
//! dhad شرح <كود>           شرح كود خطأ، مثل: dhad شرح 1003
//! dhad                      جلسة تفاعلية (REPL)
//! ```

use dhad_diagnostics::{explain, render, Diagnostic};
use dhad_interp::Interp;
use std::io::{self, BufRead, Write};
use std::process::ExitCode;

const USAGE: &str = "\
ضاد — منصة برمجة عربية

الاستخدام:
  dhad شغّل <ملف.ضاد>     تشغيل برنامج            (run)
  dhad افحص <ملف.ضاد>     فحص نحوي دون تشغيل      (check)
  dhad اختبر <ملف.ضاد>    تشغيل كتل «اختبر»       (test)
  dhad شرح <كود>          شرح كود خطأ: شرح 1003  (explain)
  dhad                     جلسة تفاعلية            (repl)

خيارات:
  --وقود <ن>  | --fuel <n>            حد أقصى لعدد خطوات التنفيذ
  --أرقام-شرقية | --eastern-digits    عرض الأرقام بالأرقام العربية الشرقية
";

struct Opts {
    fuel: Option<u64>,
    eastern: bool,
    positional: Vec<String>,
}

fn parse_opts() -> Opts {
    let mut opts = Opts {
        fuel: None,
        eastern: false,
        positional: Vec::new(),
    };
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--وقود" | "--fuel" => {
                opts.fuel = args.next().and_then(|v| v.parse().ok());
            }
            "--أرقام-شرقية" | "--eastern-digits" => opts.eastern = true,
            "-h" | "--help" | "مساعدة" | "--مساعدة" => {
                print!("{USAGE}");
                std::process::exit(0);
            }
            _ => opts.positional.push(a),
        }
    }
    opts
}

fn main() -> ExitCode {
    // المفسر تكراري؛ نشغّله في خيط بمكدس كبير حتى لا ينهار قبل حد العمق المنطقي.
    let handle = std::thread::Builder::new()
        .stack_size(256 * 1024 * 1024)
        .spawn(real_main)
        .expect("تعذّر إنشاء خيط التنفيذ");
    handle.join().unwrap_or(ExitCode::from(2))
}

fn real_main() -> ExitCode {
    let opts = parse_opts();
    let cmd = opts.positional.first().map(String::as_str);
    match cmd {
        None => repl(&opts),
        Some("شغّل" | "شغل" | "run") => run_file(&opts, false),
        Some("اختبر" | "test") => run_file(&opts, true),
        Some("افحص" | "check") => check_file(&opts),
        Some("شرح" | "explain") => explain_cmd(&opts),
        Some(path) if path.ends_with(".ضاد") || path.ends_with(".dhad") => {
            // اختصار: dhad ملف.ضاد
            let mut o = Opts {
                fuel: opts.fuel,
                eastern: opts.eastern,
                positional: vec!["شغّل".into(), path.to_string()],
            };
            o.positional.extend(opts.positional.iter().skip(1).cloned());
            run_file(&o, false)
        }
        Some(other) => {
            eprintln!("أمر غير معروف: «{other}»\n\n{USAGE}");
            ExitCode::from(2)
        }
    }
}

fn read_source(opts: &Opts) -> Result<(String, String), ExitCode> {
    let Some(path) = opts.positional.get(1) else {
        eprintln!("حدد ملفًا للتشغيل، مثل: dhad شغّل برنامج.ضاد");
        return Err(ExitCode::from(2));
    };
    match std::fs::read_to_string(path) {
        Ok(src) => Ok((path.clone(), dhad_syntax::normalize_source(&src))),
        Err(e) => {
            eprintln!("تعذّر قراءة الملف «{path}»: {e}");
            Err(ExitCode::from(2))
        }
    }
}

fn report(diag: &Diagnostic, src: &str, path: &str) {
    eprintln!("{}", render(diag, src, path));
}

fn run_file(opts: &Opts, tests: bool) -> ExitCode {
    let (path, src) = match read_source(opts) {
        Ok(v) => v,
        Err(c) => return c,
    };
    let program = match dhad_syntax::parse(&src) {
        Ok(p) => p,
        Err(e) => {
            report(&e, &src, &path);
            return ExitCode::from(1);
        }
    };
    let mut it = Interp::new(Box::new(io::stdout()));
    it.fuel = opts.fuel;
    it.eastern_digits = opts.eastern;
    if let Err(e) = it.run(&program) {
        let _ = it.out.flush();
        report(&e, &src, &path);
        return ExitCode::from(1);
    }
    if tests {
        if !it.has_tests() {
            println!("لا توجد كتل «اختبر» في {path}");
            return ExitCode::SUCCESS;
        }
        let (_, failed) = it.run_tests();
        return if failed == 0 {
            ExitCode::SUCCESS
        } else {
            ExitCode::from(1)
        };
    }
    let _ = it.out.flush();
    ExitCode::SUCCESS
}

fn check_file(opts: &Opts) -> ExitCode {
    let (path, src) = match read_source(opts) {
        Ok(v) => v,
        Err(c) => return c,
    };
    let analysis = dhad_analysis::analyze(&src);
    let errors = analysis
        .diagnostics
        .iter()
        .filter(|d| d.severity == dhad_diagnostics::Severity::Error)
        .count();
    let warnings = analysis.diagnostics.len() - errors;
    for d in &analysis.diagnostics {
        report(d, &src, &path);
    }
    if errors == 0 {
        println!("✔ {path}: لا أخطاء — {warnings} تحذير");
        ExitCode::SUCCESS
    } else {
        eprintln!("✘ {path}: {errors} خطأ — {warnings} تحذير");
        ExitCode::from(1)
    }
}

fn explain_cmd(opts: &Opts) -> ExitCode {
    let Some(code) = opts.positional.get(1) else {
        eprintln!("حدد كود الخطأ، مثل: dhad شرح 1003");
        return ExitCode::from(2);
    };
    let digits: String = code
        .chars()
        .filter_map(|c| dhad_syntax::unicode::digit_value(c).and_then(|d| char::from_digit(d, 10)))
        .collect();
    match digits.parse::<u16>().ok().and_then(explain) {
        Some(text) => {
            println!("{text}");
            ExitCode::SUCCESS
        }
        None => {
            eprintln!("لا يوجد كود خطأ بهذا الرقم: «{code}»");
            ExitCode::from(1)
        }
    }
}

fn braces_balanced(s: &str) -> bool {
    let mut depth: i32 = 0;
    let mut in_str = false;
    let mut prev = '\0';
    for c in s.chars() {
        match c {
            '"' if prev != '\\' => in_str = !in_str,
            '{' | '(' | '[' if !in_str => depth += 1,
            '}' | ')' | ']' if !in_str => depth -= 1,
            _ => {}
        }
        prev = c;
    }
    depth <= 0 && !in_str
}

fn repl(opts: &Opts) -> ExitCode {
    println!("ضاد — جلسة تفاعلية. اكتب «خروج» للإنهاء، أو «مساعدة» للأوامر.");
    let mut it = Interp::new(Box::new(io::stdout()));
    it.fuel = opts.fuel;
    it.eastern_digits = opts.eastern;
    let stdin = io::stdin();
    let mut buffer = String::new();
    loop {
        let prompt = if buffer.is_empty() {
            "ضاد> "
        } else {
            "...  "
        };
        print!("{prompt}");
        let _ = io::stdout().flush();
        let mut line = String::new();
        match stdin.lock().read_line(&mut line) {
            Ok(0) => break,
            Ok(_) => {}
            Err(_) => break,
        }
        let trimmed = line.trim();
        if buffer.is_empty() {
            match trimmed {
                "خروج" | "exit" | "quit" => break,
                "مساعدة" | "help" => {
                    print!("{USAGE}");
                    continue;
                }
                "" => continue,
                _ => {}
            }
        }
        buffer.push_str(&line);
        if !braces_balanced(&buffer) {
            continue;
        }
        let src = dhad_syntax::normalize_source(&buffer);
        buffer.clear();
        let program = match dhad_syntax::parse(&src) {
            Ok(p) => p,
            Err(e) => {
                report(&e, &src, "<جلسة>");
                continue;
            }
        };
        for stmt in &program.stmts {
            match it.exec_repl(stmt) {
                Ok(Some(v)) => {
                    if !matches!(v, dhad_interp::Value::Null) {
                        println!(
                            "{}",
                            dhad_interp::value::format_value(&v, it.eastern_digits, true)
                        );
                    }
                }
                Ok(None) => {}
                Err(e) => {
                    report(&e, &src, "<جلسة>");
                    break;
                }
            }
        }
    }
    ExitCode::SUCCESS
}
