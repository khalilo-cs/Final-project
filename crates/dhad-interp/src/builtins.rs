//! المكتبة القياسية المصغّرة: الدوال العامة والوحدات (رياضيات، نصوص، قوائم، وقت، عشوائي).

use crate::env::Env;
use crate::interp::Interp;
use crate::value::{Builtin, BuiltinFn, Value};
use dhad_diagnostics::{Diagnostic, Span};
use dhad_syntax::unicode::{digit_value, normalize_source, strip_tashkeel};
use std::io::Write;

type Res = Result<Value, Diagnostic>;

const GLOBALS: &[(&str, BuiltinFn)] = &[
    ("اطبع", print),
    ("نص", to_text),
    ("عدد", to_number),
    ("طول", len),
    ("نوع", type_of),
    ("مدى", range),
    ("أضف", push),
    ("احذف", remove),
    ("اقرأ", read_line),
    ("تأكد", assert),
    ("أكبر", max),
    ("أصغر", min),
    ("مطلق", abs),
    ("تقريب", round),
    ("جذر", sqrt),
];

pub fn install_globals(env: &Env) {
    for (name, func) in GLOBALS {
        env.define(name, Value::Builtin(Builtin { name, func: *func }), true);
    }
}

fn module_dict(
    name: &'static str,
    entries: &[(&'static str, BuiltinFn)],
    consts: &[(&str, Value)],
) -> Value {
    let mut pairs: Vec<(Value, Value)> = entries
        .iter()
        .map(|(n, f)| {
            (
                Value::str(strip_tashkeel(n)),
                Value::Builtin(Builtin { name: n, func: *f }),
            )
        })
        .collect();
    // المعرّفات تُطبَّع بحذف التشكيل في المحلل، فتُخزَّن المفاتيح بالتطبيع نفسه.
    pairs.extend(
        consts
            .iter()
            .map(|(n, v)| (Value::str(strip_tashkeel(n)), v.clone())),
    );
    pairs.push((Value::str("__اسم__"), Value::str(name)));
    Value::dict(pairs)
}

/// الوحدات المتاحة لـ «استورد».
pub fn module(name: &str) -> Option<Value> {
    Some(match name {
        "رياضيات" => module_dict(
            "رياضيات",
            &[
                ("جذر", sqrt),
                ("قوة", pow),
                ("مطلق", abs),
                ("تقريب", round),
                ("سقف", ceil),
                ("أرضية", floor),
                ("أكبر", max),
                ("أصغر", min),
            ],
            &[
                ("ط", Value::Float(std::f64::consts::PI)),
                ("هـ", Value::Float(std::f64::consts::E)),
            ],
        ),
        "نصوص" => module_dict(
            "نصوص",
            &[
                ("قسّم", split),
                ("اربط", join),
                ("استبدل", replace),
                ("يبدأ_بـ", starts_with),
                ("ينتهي_بـ", ends_with),
                ("يحتوي", contains),
                ("احذف_التشكيل", remove_tashkeel),
                ("طبّع", normalize),
                ("اقلب", reverse_text),
                ("قصّ", trim),
            ],
            &[],
        ),
        "قوائم" => module_dict(
            "قوائم",
            &[
                ("رتّب", sort),
                ("اعكس", reverse_list),
                ("اجمع", sum),
                ("أضف", push),
                ("احذف", remove),
                ("يحتوي", contains),
            ],
            &[],
        ),
        "وقت" => module_dict("وقت", &[("الآن", now), ("انتظر", sleep)], &[]),
        "عشوائي" => module_dict(
            "عشوائي",
            &[("عدد_عشوائي", random_int), ("اختر", choose)],
            &[],
        ),
        _ => return None,
    })
}

// ---------- مساعدات ----------

fn arity(args: &[Value], n: usize, name: &str, span: Span) -> Result<(), Diagnostic> {
    if args.len() != n {
        return Err(Diagnostic::error(
            1004,
            format!(
                "الدالة «{name}» تتوقع {n} من المعاملات لكنها تلقّت {}",
                args.len()
            ),
        )
        .with_span(span));
    }
    Ok(())
}

fn type_err(name: &str, expected: &str, got: &Value, span: Span) -> Diagnostic {
    Diagnostic::error(
        2007,
        format!(
            "الدالة «{name}» تتوقع {expected} لكنها تلقّت قيمة من نوع {}",
            got.type_name()
        ),
    )
    .with_span(span)
}

fn num(v: &Value, name: &str, span: Span) -> Result<f64, Diagnostic> {
    v.as_f64().ok_or_else(|| type_err(name, "عددًا", v, span))
}

fn text<'a>(v: &'a Value, name: &str, span: Span) -> Result<&'a str, Diagnostic> {
    match v {
        Value::Str(s) => Ok(s),
        other => Err(type_err(name, "نصًا", other, span)),
    }
}

fn list(v: &Value, name: &str, span: Span) -> Result<crate::value::ListRef, Diagnostic> {
    match v {
        Value::List(l) => Ok(l.clone()),
        other => Err(type_err(name, "قائمة", other, span)),
    }
}

fn float_or_int(f: f64) -> Value {
    if f.fract() == 0.0 && f.abs() < 9e15 {
        Value::Int(f as i64)
    } else {
        Value::Float(f)
    }
}

// ---------- الدوال العامة ----------

fn print(it: &mut Interp, args: Vec<Value>, _span: Span) -> Res {
    let line = args
        .iter()
        .map(|v| it.display(v))
        .collect::<Vec<_>>()
        .join(" ");
    let _ = writeln!(it.out, "{line}");
    Ok(Value::Null)
}

fn to_text(it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "نص", span)?;
    Ok(Value::str(it.display(&args[0])))
}

fn to_number(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "عدد", span)?;
    match &args[0] {
        Value::Int(_) | Value::Float(_) => Ok(args[0].clone()),
        Value::Bool(b) => Ok(Value::Int(*b as i64)),
        Value::Str(s) => {
            let cleaned: String = s
                .trim()
                .chars()
                .map(|c| match digit_value(c) {
                    Some(d) => char::from_digit(d, 10).unwrap(),
                    None if c == '\u{066B}' => '.',
                    None if c == '\u{2212}' => '-',
                    None => c,
                })
                .collect();
            if let Ok(n) = cleaned.parse::<i64>() {
                Ok(Value::Int(n))
            } else if let Ok(f) = cleaned.parse::<f64>() {
                Ok(Value::Float(f))
            } else {
                Err(
                    Diagnostic::error(2008, format!("تعذّر تحويل النص «{s}» إلى عدد"))
                        .with_span(span),
                )
            }
        }
        other => Err(type_err("عدد", "نصًا أو عددًا", other, span)),
    }
}

fn len(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "طول", span)?;
    Ok(Value::Int(match &args[0] {
        Value::Str(s) => s.chars().count() as i64,
        Value::List(l) => l.borrow().len() as i64,
        Value::Dict(d) => d.borrow().len() as i64,
        Value::Range(a, b) => (b - a).max(0),
        other => return Err(type_err("طول", "نصًا أو قائمة أو قاموسًا", other, span)),
    }))
}

fn type_of(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "نوع", span)?;
    Ok(Value::str(args[0].type_name()))
}

fn range(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    let (a, b) = match args.as_slice() {
        [Value::Int(b)] => (0, *b),
        [Value::Int(a), Value::Int(b)] => (*a, *b),
        _ => {
            return Err(
                Diagnostic::error(2007, "الدالة «مدى» تتوقع عددًا صحيحًا أو عددين صحيحين")
                    .with_span(span),
            )
        }
    };
    Ok(Value::Range(a, b))
}

fn push(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 2, "أضف", span)?;
    let l = list(&args[0], "أضف", span)?;
    l.borrow_mut().push(args[1].clone());
    Ok(Value::Null)
}

fn remove(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 2, "احذف", span)?;
    match &args[0] {
        Value::List(l) => {
            let len = l.borrow().len();
            let idx = crate::interp::list_index(&args[1], len, span)?;
            Ok(l.borrow_mut().remove(idx))
        }
        Value::Dict(d) => {
            let mut d = d.borrow_mut();
            let pos = d.iter().position(|(k, _)| k.equals(&args[1]));
            Ok(match pos {
                Some(p) => d.remove(p).1,
                None => Value::Null,
            })
        }
        other => Err(type_err("احذف", "قائمة أو قاموسًا", other, span)),
    }
}

fn read_line(it: &mut Interp, args: Vec<Value>, _span: Span) -> Res {
    if let Some(prompt) = args.first() {
        let p = it.display(prompt);
        let _ = write!(it.out, "{p}");
    }
    let _ = it.out.flush();
    let mut line = String::new();
    std::io::stdin().read_line(&mut line).ok();
    Ok(Value::str(line.trim_end_matches(['\n', '\r'])))
}

fn assert(it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    match args.first() {
        Some(Value::Bool(true)) => Ok(Value::Null),
        Some(Value::Bool(false)) => {
            let msg = match args.get(1) {
                Some(m) => format!("فشل التأكيد: {}", it.display(m)),
                None => "فشل التأكيد".to_string(),
            };
            Err(Diagnostic::error(2006, msg).with_span(span))
        }
        Some(other) => Err(type_err("تأكد", "قيمة منطقية", other, span)),
        None => {
            Err(Diagnostic::error(1004, "الدالة «تأكد» تتوقع معاملًا واحدًا على الأقل").with_span(span))
        }
    }
}

fn minmax(args: &[Value], name: &str, span: Span, want_max: bool) -> Res {
    let items: Vec<Value> = match args {
        [Value::List(l)] => l.borrow().clone(),
        _ => args.to_vec(),
    };
    if items.is_empty() {
        return Err(Diagnostic::error(
            1004,
            format!("الدالة «{name}» تحتاج إلى قيمة واحدة على الأقل"),
        )
        .with_span(span));
    }
    let mut best = items[0].clone();
    for v in &items[1..] {
        let (a, b) = (num(&best, name, span)?, num(v, name, span)?);
        if (want_max && b > a) || (!want_max && b < a) {
            best = v.clone();
        }
    }
    Ok(best)
}

fn max(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    minmax(&args, "أكبر", span, true)
}

fn min(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    minmax(&args, "أصغر", span, false)
}

fn abs(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "مطلق", span)?;
    Ok(match &args[0] {
        Value::Int(n) => Value::Int(n.abs()),
        other => Value::Float(num(other, "مطلق", span)?.abs()),
    })
}

fn round(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    if args.len() == 2 {
        let x = num(&args[0], "تقريب", span)?;
        let d = num(&args[1], "تقريب", span)? as i32;
        let m = 10f64.powi(d);
        return Ok(Value::Float((x * m).round() / m));
    }
    arity(&args, 1, "تقريب", span)?;
    Ok(Value::Int(num(&args[0], "تقريب", span)?.round() as i64))
}

fn sqrt(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "جذر", span)?;
    let x = num(&args[0], "جذر", span)?;
    if x < 0.0 {
        return Err(Diagnostic::error(2007, "الجذر التربيعي لعدد سالب غير معرَّف").with_span(span));
    }
    Ok(float_or_int(x.sqrt()))
}

fn pow(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 2, "قوة", span)?;
    match (&args[0], &args[1]) {
        (Value::Int(a), Value::Int(b)) if *b >= 0 => Ok(a
            .checked_pow(*b as u32)
            .map(Value::Int)
            .unwrap_or(Value::Float((*a as f64).powf(*b as f64)))),
        (a, b) => Ok(Value::Float(
            num(a, "قوة", span)?.powf(num(b, "قوة", span)?),
        )),
    }
}

fn ceil(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "سقف", span)?;
    Ok(Value::Int(num(&args[0], "سقف", span)?.ceil() as i64))
}

fn floor(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "أرضية", span)?;
    Ok(Value::Int(num(&args[0], "أرضية", span)?.floor() as i64))
}

// ---------- نصوص ----------

fn split(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    let s = text(args.first().unwrap_or(&Value::Null), "قسّم", span)?;
    let parts: Vec<Value> = match args.get(1) {
        Some(sep) => {
            let sep = text(sep, "قسّم", span)?;
            s.split(sep).map(Value::str).collect()
        }
        None => s.split_whitespace().map(Value::str).collect(),
    };
    Ok(Value::list(parts))
}

fn join(it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    let l = list(args.first().unwrap_or(&Value::Null), "اربط", span)?;
    let sep = match args.get(1) {
        Some(s) => text(s, "اربط", span)?.to_string(),
        None => String::new(),
    };
    let joined = l
        .borrow()
        .iter()
        .map(|v| it.display(v))
        .collect::<Vec<_>>()
        .join(&sep);
    Ok(Value::str(joined))
}

fn replace(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 3, "استبدل", span)?;
    let s = text(&args[0], "استبدل", span)?;
    let from = text(&args[1], "استبدل", span)?;
    let to = text(&args[2], "استبدل", span)?;
    Ok(Value::str(s.replace(from, to)))
}

fn starts_with(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 2, "يبدأ_بـ", span)?;
    Ok(Value::Bool(
        text(&args[0], "يبدأ_بـ", span)?.starts_with(text(&args[1], "يبدأ_بـ", span)?),
    ))
}

fn ends_with(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 2, "ينتهي_بـ", span)?;
    Ok(Value::Bool(
        text(&args[0], "ينتهي_بـ", span)?.ends_with(text(&args[1], "ينتهي_بـ", span)?),
    ))
}

fn contains(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 2, "يحتوي", span)?;
    Ok(Value::Bool(match (&args[0], &args[1]) {
        (Value::Str(s), Value::Str(sub)) => s.contains(&**sub),
        (Value::List(l), x) => l.borrow().iter().any(|v| v.equals(x)),
        (Value::Dict(d), k) => crate::value::dict_lookup(&d.borrow(), k).is_some(),
        (other, _) => return Err(type_err("يحتوي", "نصًا أو قائمة", other, span)),
    }))
}

fn remove_tashkeel(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "احذف_التشكيل", span)?;
    Ok(Value::str(strip_tashkeel(text(
        &args[0],
        "احذف_التشكيل",
        span,
    )?)))
}

fn normalize(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "طبّع", span)?;
    Ok(Value::str(normalize_source(text(&args[0], "طبّع", span)?)))
}

fn reverse_text(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "اقلب", span)?;
    Ok(Value::str(
        text(&args[0], "اقلب", span)?
            .chars()
            .rev()
            .collect::<String>(),
    ))
}

fn trim(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "قصّ", span)?;
    Ok(Value::str(text(&args[0], "قصّ", span)?.trim()))
}

// ---------- قوائم ----------

fn sort(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "رتّب", span)?;
    let l = list(&args[0], "رتّب", span)?;
    let mut items = l.borrow().clone();
    let all_text = items.iter().all(|v| matches!(v, Value::Str(_)));
    let all_num = items.iter().all(|v| v.as_f64().is_some());
    if !(all_text || all_num) {
        return Err(
            Diagnostic::error(1008, "لا يمكن ترتيب قائمة تخلط أنواعًا مختلفة").with_span(span),
        );
    }
    items.sort_by(|a, b| match (a, b) {
        (Value::Str(x), Value::Str(y)) => x.cmp(y),
        _ => a
            .as_f64()
            .partial_cmp(&b.as_f64())
            .unwrap_or(std::cmp::Ordering::Equal),
    });
    Ok(Value::list(items))
}

fn reverse_list(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "اعكس", span)?;
    let l = list(&args[0], "اعكس", span)?;
    let mut items = l.borrow().clone();
    items.reverse();
    Ok(Value::list(items))
}

fn sum(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "اجمع", span)?;
    let l = list(&args[0], "اجمع", span)?;
    let mut total_i: i64 = 0;
    let mut total_f: f64 = 0.0;
    let mut is_float = false;
    for v in l.borrow().iter() {
        match v {
            Value::Int(n) => match total_i.checked_add(*n) {
                Some(t) => total_i = t,
                None => {
                    is_float = true;
                    total_f += *n as f64;
                }
            },
            Value::Float(f) => {
                is_float = true;
                total_f += f;
            }
            other => return Err(type_err("اجمع", "قائمة أعداد", other, span)),
        }
    }
    Ok(if is_float {
        Value::Float(total_f + total_i as f64)
    } else {
        Value::Int(total_i)
    })
}

// ---------- وقت وعشوائي ----------

fn now(it: &mut Interp, _args: Vec<Value>, _span: Span) -> Res {
    Ok(Value::Float(it.now_ms()))
}

fn sleep(_it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "انتظر", span)?;
    let ms = num(&args[0], "انتظر", span)?.max(0.0);
    #[cfg(not(target_arch = "wasm32"))]
    std::thread::sleep(std::time::Duration::from_millis(ms as u64));
    #[cfg(target_arch = "wasm32")]
    let _ = ms;
    Ok(Value::Null)
}

fn next_random(it: &mut Interp) -> u64 {
    // xorshift64*
    let mut x = it.rng;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    it.rng = x;
    x.wrapping_mul(0x2545_F491_4F6C_DD1D)
}

fn random_int(it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 2, "عدد_عشوائي", span)?;
    let (a, b) = match (&args[0], &args[1]) {
        (Value::Int(a), Value::Int(b)) if a <= b => (*a, *b),
        _ => {
            return Err(Diagnostic::error(
                2007,
                "الدالة «عدد_عشوائي» تتوقع حدين صحيحين (الأدنى ثم الأعلى)",
            )
            .with_span(span))
        }
    };
    let span_len = (b - a + 1) as u64;
    Ok(Value::Int(a + (next_random(it) % span_len) as i64))
}

fn choose(it: &mut Interp, args: Vec<Value>, span: Span) -> Res {
    arity(&args, 1, "اختر", span)?;
    let l = list(&args[0], "اختر", span)?;
    let items = l.borrow();
    if items.is_empty() {
        return Err(Diagnostic::error(2002, "لا يمكن الاختيار من قائمة فارغة").with_span(span));
    }
    let idx = (next_random(it) % items.len() as u64) as usize;
    Ok(items[idx].clone())
}
