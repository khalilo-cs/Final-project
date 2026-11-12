//! قيم وقت التشغيل.

use crate::env::Env;
use crate::interp::Interp;
use dhad_diagnostics::{to_eastern_digits, Diagnostic, Span};
use dhad_syntax::Block;
use std::cell::RefCell;
use std::rc::Rc;

pub type BuiltinFn = fn(&mut Interp, Vec<Value>, Span) -> Result<Value, Diagnostic>;

#[derive(Clone, Copy)]
pub struct Builtin {
    pub name: &'static str,
    pub func: BuiltinFn,
}

pub struct Function {
    pub name: String,
    pub params: Vec<String>,
    pub body: Block,
    pub closure: Env,
}

pub type ListRef = Rc<RefCell<Vec<Value>>>;
pub type DictRef = Rc<RefCell<Vec<(Value, Value)>>>;

#[derive(Clone)]
pub enum Value {
    Int(i64),
    Float(f64),
    Str(Rc<str>),
    Bool(bool),
    Null,
    List(ListRef),
    Dict(DictRef),
    /// مدى نصف مفتوح: من..إلى
    Range(i64, i64),
    Func(Rc<Function>),
    Builtin(Builtin),
}

impl Value {
    pub fn str(s: impl Into<Rc<str>>) -> Value {
        Value::Str(s.into())
    }

    pub fn list(items: Vec<Value>) -> Value {
        Value::List(Rc::new(RefCell::new(items)))
    }

    pub fn dict(pairs: Vec<(Value, Value)>) -> Value {
        Value::Dict(Rc::new(RefCell::new(pairs)))
    }

    pub fn type_name(&self) -> &'static str {
        match self {
            Value::Int(_) => "عدد_صحيح",
            Value::Float(_) => "عدد_عشري",
            Value::Str(_) => "نص",
            Value::Bool(_) => "منطقي",
            Value::Null => "عدم",
            Value::List(_) => "قائمة",
            Value::Dict(_) => "قاموس",
            Value::Range(_, _) => "مدى",
            Value::Func(_) | Value::Builtin(_) => "دالة",
        }
    }

    pub fn as_f64(&self) -> Option<f64> {
        match self {
            Value::Int(n) => Some(*n as f64),
            Value::Float(f) => Some(*f),
            _ => None,
        }
    }

    pub fn equals(&self, other: &Value) -> bool {
        use Value::*;
        match (self, other) {
            (Int(a), Int(b)) => a == b,
            (Float(a), Float(b)) => a == b,
            (Int(a), Float(b)) | (Float(b), Int(a)) => (*a as f64) == *b,
            (Str(a), Str(b)) => a == b,
            (Bool(a), Bool(b)) => a == b,
            (Null, Null) => true,
            (Range(a1, b1), Range(a2, b2)) => a1 == a2 && b1 == b2,
            (List(a), List(b)) => {
                if Rc::ptr_eq(a, b) {
                    return true;
                }
                let (a, b) = (a.borrow(), b.borrow());
                a.len() == b.len() && a.iter().zip(b.iter()).all(|(x, y)| x.equals(y))
            }
            (Dict(a), Dict(b)) => {
                if Rc::ptr_eq(a, b) {
                    return true;
                }
                let (a, b) = (a.borrow(), b.borrow());
                a.len() == b.len()
                    && a.iter()
                        .all(|(k, v)| dict_lookup(&b, k).is_some_and(|v2| v.equals(&v2)))
            }
            (Func(a), Func(b)) => Rc::ptr_eq(a, b),
            (Builtin(a), Builtin(b)) => a.name == b.name,
            _ => false,
        }
    }
}

pub fn dict_lookup(pairs: &[(Value, Value)], key: &Value) -> Option<Value> {
    pairs
        .iter()
        .find(|(k, _)| k.equals(key))
        .map(|(_, v)| v.clone())
}

pub fn dict_set(dict: &DictRef, key: Value, value: Value) {
    let mut d = dict.borrow_mut();
    if let Some(slot) = d.iter_mut().find(|(k, _)| k.equals(&key)) {
        slot.1 = value;
    } else {
        d.push((key, value));
    }
}

fn fmt_float(f: f64) -> String {
    if f.is_finite() && f.fract() == 0.0 && f.abs() < 1e15 {
        format!("{f:.1}")
    } else if f.is_nan() {
        "ليس_عددًا".to_string()
    } else if f.is_infinite() {
        if f > 0.0 {
            "∞".into()
        } else {
            "-∞".into()
        }
    } else {
        format!("{f}")
    }
}

/// تنسيق قيمة للعرض. `quoted` يضع النصوص بين علامتي اقتباس (داخل القوائم مثلًا).
pub fn format_value(v: &Value, eastern: bool, quoted: bool) -> String {
    let digits = |s: String| if eastern { to_eastern_digits(&s) } else { s };
    match v {
        Value::Int(n) => digits(n.to_string()),
        Value::Float(f) => digits(fmt_float(*f)),
        Value::Str(s) => {
            if quoted {
                format!("\"{s}\"")
            } else {
                s.to_string()
            }
        }
        Value::Bool(true) => "صحيح".into(),
        Value::Bool(false) => "خطأ".into(),
        Value::Null => "عدم".into(),
        Value::List(items) => {
            let inner: Vec<String> = items
                .borrow()
                .iter()
                .map(|x| format_value(x, eastern, true))
                .collect();
            format!("[{}]", inner.join("، "))
        }
        Value::Dict(pairs) => {
            let inner: Vec<String> = pairs
                .borrow()
                .iter()
                .map(|(k, v)| {
                    format!(
                        "{}: {}",
                        format_value(k, eastern, true),
                        format_value(v, eastern, true)
                    )
                })
                .collect();
            format!("{{{}}}", inner.join("، "))
        }
        Value::Range(a, b) => digits(format!("{a}..{b}")),
        Value::Func(f) => format!("<دالة {}>", f.name),
        Value::Builtin(b) => format!("<دالة مدمجة {}>", b.name),
    }
}
