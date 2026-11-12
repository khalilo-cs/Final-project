//! نواة التنفيذ.

use crate::builtins;
use crate::env::{AssignErr, Env};
use crate::value::{dict_lookup, dict_set, format_value, Function, Value};
use dhad_diagnostics::{Diagnostic, Span};
use dhad_syntax::*;
use std::io::Write;
use std::rc::Rc;

const MAX_DEPTH: usize = 1000;

/// تدفق التحكم غير الاعتيادي داخل التنفيذ.
pub enum Flow {
    Return(Value),
    Break,
    Continue,
    Err(Diagnostic),
}

impl From<Diagnostic> for Flow {
    fn from(d: Diagnostic) -> Self {
        Flow::Err(d)
    }
}

type R<T> = Result<T, Flow>;

struct TestCase {
    name: String,
    body: Block,
    env: Env,
}

pub struct Interp {
    pub globals: Env,
    pub out: Box<dyn Write>,
    /// عرض الأرقام بالأرقام العربية الشرقية في المخرجات.
    pub eastern_digits: bool,
    /// الحد الأقصى لعدد الخطوات (عدّاد الوقود). `None` = بلا حد.
    pub fuel: Option<u64>,
    steps: u64,
    depth: usize,
    tests: Vec<TestCase>,
    pub(crate) rng: u64,
    clock: fn() -> f64,
}

/// الوقت بالمللي ثانية منذ 1970. على wasm32 لا توجد ساعة نظام، فيُعاد صفر
/// حتى يمرر المضيف ساعته عبر [`Interp::set_clock`].
pub fn system_clock_ms() -> f64 {
    #[cfg(not(target_arch = "wasm32"))]
    {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs_f64() * 1000.0)
            .unwrap_or(0.0)
    }
    #[cfg(target_arch = "wasm32")]
    {
        0.0
    }
}

impl Interp {
    pub fn new(out: Box<dyn Write>) -> Self {
        let globals = Env::new();
        builtins::install_globals(&globals);
        let clock: fn() -> f64 = system_clock_ms;
        let seed = (clock().to_bits() ^ 0x9E37_79B9_7F4A_7C15) | 1;
        Interp {
            globals,
            out,
            eastern_digits: false,
            fuel: None,
            steps: 0,
            depth: 0,
            tests: Vec::new(),
            rng: seed,
            clock,
        }
    }

    /// استبدال مصدر الوقت (يستخدمه مضيف WebAssembly لتمرير ساعة المتصفح).
    pub fn set_clock(&mut self, clock: fn() -> f64) {
        self.clock = clock;
        self.rng = (clock().to_bits() ^ 0x9E37_79B9_7F4A_7C15) | 1;
    }

    /// تثبيت بذرة المولد العشوائي (للاختبارات القابلة لإعادة الإنتاج).
    pub fn seed(&mut self, seed: u64) {
        self.rng = seed | 1;
    }

    pub fn now_ms(&self) -> f64 {
        (self.clock)()
    }

    pub fn steps(&self) -> u64 {
        self.steps
    }

    pub fn display(&self, v: &Value) -> String {
        format_value(v, self.eastern_digits, false)
    }

    /// تنفيذ برنامج كامل في النطاق العام.
    pub fn run(&mut self, program: &Program) -> Result<(), Diagnostic> {
        let env = self.globals.clone();
        for stmt in &program.stmts {
            self.exec_stmt(stmt, &env)
                .map_err(|f| self.flow_to_diag(f, stmt.span))?;
        }
        Ok(())
    }

    /// تنفيذ جملة واحدة في النطاق العام وإرجاع قيمتها إن كانت تعبيرًا (لـ REPL).
    pub fn exec_repl(&mut self, stmt: &Stmt) -> Result<Option<Value>, Diagnostic> {
        let env = self.globals.clone();
        match &stmt.kind {
            StmtKind::Expr(e) => {
                self.tick(stmt.span)
                    .map_err(|f| self.flow_to_diag(f, stmt.span))?;
                let v = self
                    .eval(e, &env)
                    .map_err(|f| self.flow_to_diag(f, e.span))?;
                Ok(Some(v))
            }
            _ => {
                self.exec_stmt(stmt, &env)
                    .map_err(|f| self.flow_to_diag(f, stmt.span))?;
                Ok(None)
            }
        }
    }

    /// تشغيل كتل «اختبر» المسجلة. يعيد (نجح، فشل).
    pub fn run_tests(&mut self) -> (usize, usize) {
        let tests = std::mem::take(&mut self.tests);
        let (mut passed, mut failed) = (0, 0);
        for t in tests {
            match self.exec_block(&t.body, &t.env) {
                Ok(()) => {
                    passed += 1;
                    let _ = writeln!(self.out, "✔ {}", t.name);
                }
                Err(flow) => {
                    failed += 1;
                    let d = self.flow_to_diag(flow, t.body.span);
                    let _ = writeln!(self.out, "✘ {}: {}", t.name, d);
                }
            }
        }
        let _ = writeln!(
            self.out,
            "النتيجة: نجح {} — فشل {}",
            self.display(&Value::Int(passed as i64)),
            self.display(&Value::Int(failed as i64))
        );
        (passed, failed)
    }

    pub fn has_tests(&self) -> bool {
        !self.tests.is_empty()
    }

    fn flow_to_diag(&self, f: Flow, span: Span) -> Diagnostic {
        match f {
            Flow::Err(d) => d,
            Flow::Return(_) => Diagnostic::error(1006, "«أرجع» خارج دالة").with_span(span),
            Flow::Break => Diagnostic::error(1007, "«توقف» خارج حلقة").with_span(span),
            Flow::Continue => Diagnostic::error(1007, "«استمر» خارج حلقة").with_span(span),
        }
    }

    fn tick(&mut self, span: Span) -> R<()> {
        self.steps += 1;
        if let Some(limit) = self.fuel {
            if self.steps > limit {
                return Err(Diagnostic::error(
                    2005,
                    format!("تجاوز البرنامج حد التنفيذ ({limit} خطوة)"),
                )
                .with_span(span)
                .into());
            }
        }
        Ok(())
    }

    fn exec_block(&mut self, block: &Block, env: &Env) -> R<()> {
        let scope = env.child();
        for s in &block.stmts {
            self.exec_stmt(s, &scope)?;
        }
        Ok(())
    }

    fn exec_stmt(&mut self, stmt: &Stmt, env: &Env) -> R<()> {
        self.tick(stmt.span)?;
        match &stmt.kind {
            StmtKind::Let {
                name,
                value,
                is_const,
                ..
            } => {
                let v = self.eval(value, env)?;
                env.define(name, v, *is_const);
            }
            StmtKind::Assign { target, value } => {
                let v = self.eval(value, env)?;
                self.assign(target, v, env)?;
            }
            StmtKind::If {
                cond,
                then,
                elifs,
                otherwise,
            } => {
                if self.cond(cond, env)? {
                    self.exec_block(then, env)?;
                } else {
                    for (c, b) in elifs {
                        if self.cond(c, env)? {
                            return self.exec_block(b, env);
                        }
                    }
                    if let Some(b) = otherwise {
                        self.exec_block(b, env)?;
                    }
                }
            }
            StmtKind::While { cond, body } => loop {
                if !self.cond(cond, env)? {
                    break;
                }
                self.tick(stmt.span)?;
                match self.exec_block(body, env) {
                    Ok(()) | Err(Flow::Continue) => {}
                    Err(Flow::Break) => break,
                    Err(e) => return Err(e),
                }
            },
            StmtKind::For {
                var, iter, body, ..
            } => {
                let it = self.eval(iter, env)?;
                let mut iterator = Iter::new(it, iter.span)?;
                for item in iterator.by_ref() {
                    self.tick(stmt.span)?;
                    let scope = env.child();
                    scope.define(var, item, false);
                    match self.exec_block(body, &scope) {
                        Ok(()) | Err(Flow::Continue) => {}
                        Err(Flow::Break) => break,
                        Err(e) => return Err(e),
                    }
                }
            }
            StmtKind::FnDecl { name, params, body } => {
                let f = Function {
                    name: name.clone(),
                    params: params.iter().map(|(p, _)| p.clone()).collect(),
                    body: body.clone(),
                    closure: env.clone(),
                };
                env.define(name, Value::Func(Rc::new(f)), false);
            }
            StmtKind::Return(e) => {
                let v = match e {
                    Some(e) => self.eval(e, env)?,
                    None => Value::Null,
                };
                return Err(Flow::Return(v));
            }
            StmtKind::Break => return Err(Flow::Break),
            StmtKind::Continue => return Err(Flow::Continue),
            StmtKind::Import { path } => {
                let name = &path[0];
                match builtins::module(name) {
                    Some(m) => env.define(name, m, true),
                    None => {
                        return Err(
                            Diagnostic::error(1009, format!("الوحدة «{name}» غير موجودة"))
                                .with_span(stmt.span)
                                .into(),
                        )
                    }
                }
            }
            StmtKind::Test { name, body } => self.tests.push(TestCase {
                name: name.clone(),
                body: body.clone(),
                env: env.clone(),
            }),
            StmtKind::Expr(e) => {
                self.eval(e, env)?;
            }
        }
        Ok(())
    }

    fn cond(&mut self, e: &Expr, env: &Env) -> R<bool> {
        match self.eval(e, env)? {
            Value::Bool(b) => Ok(b),
            other => Err(Diagnostic::error(
                1010,
                format!(
                    "الشرط يجب أن يكون صحيح أو خطأ، لكنه قيمة من نوع {}",
                    other.type_name()
                ),
            )
            .with_span(e.span)
            .into()),
        }
    }

    fn undefined(&self, name: &str, env: &Env, span: Span) -> Flow {
        let mut d = Diagnostic::error(1001, format!("المتغير «{name}» غير معرَّف"));
        let suggestion = env
            .visible_names()
            .into_iter()
            .filter(|n| !n.is_empty())
            .map(|n| (levenshtein(name, &n), n))
            .filter(|(dist, n)| *dist <= 2.max(n.chars().count() / 3) && *dist > 0)
            .min_by_key(|(dist, _)| *dist)
            .map(|(_, n)| n);
        d = match suggestion {
            Some(s) => d.with_help(format!("هل تقصد «{s}»؟ وإلا عرّفه أولًا بـ: دع {name} = ...")),
            None => d.with_help(format!("عرّفه أولًا بـ: دع {name} = ...")),
        };
        d.with_span(span).into()
    }

    fn assign(&mut self, target: &Expr, v: Value, env: &Env) -> R<()> {
        match &target.kind {
            ExprKind::Ident(name) => match env.assign(name, v) {
                Ok(()) => Ok(()),
                Err(AssignErr::NotFound) => Err(self.undefined(name, env, target.span)),
                Err(AssignErr::Const) => Err(Diagnostic::error(
                    1002,
                    format!("«{name}» ثابت ولا يمكن تغيير قيمته"),
                )
                .with_span(target.span)
                .into()),
            },
            ExprKind::Index { obj, index } => {
                let o = self.eval(obj, env)?;
                let i = self.eval(index, env)?;
                match o {
                    Value::List(l) => {
                        let len = l.borrow().len();
                        let idx = list_index(&i, len, index.span)?;
                        l.borrow_mut()[idx] = v;
                        Ok(())
                    }
                    Value::Dict(d) => {
                        dict_set(&d, i, v);
                        Ok(())
                    }
                    other => Err(Diagnostic::error(
                        2007,
                        format!("لا يمكن الفهرسة في قيمة من نوع {}", other.type_name()),
                    )
                    .with_span(obj.span)
                    .into()),
                }
            }
            ExprKind::Member { obj, name } => {
                let o = self.eval(obj, env)?;
                match o {
                    Value::Dict(d) => {
                        dict_set(&d, Value::str(name.as_str()), v);
                        Ok(())
                    }
                    other => Err(Diagnostic::error(
                        2007,
                        format!("القيمة من نوع {} لا تملك أعضاء", other.type_name()),
                    )
                    .with_span(obj.span)
                    .into()),
                }
            }
            _ => Err(Diagnostic::error(1012, "لا يمكن الإسناد إلى هذا التعبير")
                .with_span(target.span)
                .into()),
        }
    }

    pub fn eval(&mut self, e: &Expr, env: &Env) -> R<Value> {
        Ok(match &e.kind {
            ExprKind::Int(n) => Value::Int(*n),
            ExprKind::Float(f) => Value::Float(*f),
            ExprKind::Bool(b) => Value::Bool(*b),
            ExprKind::Null => Value::Null,
            ExprKind::Str(segs) => {
                let mut s = String::new();
                for seg in segs {
                    match seg {
                        StrSeg::Text(t) => s.push_str(t),
                        StrSeg::Expr(x) => {
                            let v = self.eval(x, env)?;
                            s.push_str(&self.display(&v));
                        }
                    }
                }
                Value::str(s)
            }
            ExprKind::Ident(name) => match env.get(name) {
                Some(v) => v,
                None => return Err(self.undefined(name, env, e.span)),
            },
            ExprKind::List(items) => {
                let mut out = Vec::with_capacity(items.len());
                for item in items {
                    out.push(self.eval(item, env)?);
                }
                Value::list(out)
            }
            ExprKind::Dict(pairs) => {
                let mut out = Vec::with_capacity(pairs.len());
                for (k, v) in pairs {
                    let k = self.eval(k, env)?;
                    let v = self.eval(v, env)?;
                    out.push((k, v));
                }
                Value::dict(out)
            }
            ExprKind::Binary { op, left, right } => match op {
                BinOp::And | BinOp::Or => {
                    let l = self.eval(left, env)?;
                    let Value::Bool(lb) = l else {
                        return Err(logic_type_error(*op, &l, left.span));
                    };
                    if (*op == BinOp::And && !lb) || (*op == BinOp::Or && lb) {
                        return Ok(Value::Bool(lb));
                    }
                    let r = self.eval(right, env)?;
                    let Value::Bool(rb) = r else {
                        return Err(logic_type_error(*op, &r, right.span));
                    };
                    Value::Bool(rb)
                }
                _ => {
                    let l = self.eval(left, env)?;
                    let r = self.eval(right, env)?;
                    self.binary(*op, l, r, e.span)?
                }
            },
            ExprKind::Unary { op, expr } => {
                let v = self.eval(expr, env)?;
                match (op, &v) {
                    (UnOp::Neg, Value::Int(n)) => Value::Int(n.wrapping_neg()),
                    (UnOp::Neg, Value::Float(f)) => Value::Float(-f),
                    (UnOp::Not, Value::Bool(b)) => Value::Bool(!b),
                    (UnOp::Neg, other) => {
                        return Err(Diagnostic::error(
                            1011,
                            format!("لا يمكن تطبيق السالب على قيمة من نوع {}", other.type_name()),
                        )
                        .with_span(e.span)
                        .into())
                    }
                    (UnOp::Not, other) => {
                        return Err(Diagnostic::error(
                            1011,
                            format!("«ليس» تتطلب قيمة منطقية، لا {}", other.type_name()),
                        )
                        .with_span(e.span)
                        .into())
                    }
                }
            }
            ExprKind::Call { callee, args } => {
                let f = self.eval(callee, env)?;
                let mut argv = Vec::with_capacity(args.len());
                for a in args {
                    argv.push(self.eval(a, env)?);
                }
                self.call(f, argv, e.span)?
            }
            ExprKind::Index { obj, index } => {
                let o = self.eval(obj, env)?;
                let i = self.eval(index, env)?;
                match o {
                    Value::List(l) => {
                        let len = l.borrow().len();
                        let idx = list_index(&i, len, index.span)?;
                        l.borrow()[idx].clone()
                    }
                    Value::Str(s) => {
                        let len = s.chars().count();
                        let idx = list_index(&i, len, index.span)?;
                        Value::str(s.chars().nth(idx).unwrap().to_string())
                    }
                    Value::Dict(d) => match dict_lookup(&d.borrow(), &i) {
                        Some(v) => v,
                        None => {
                            return Err(Diagnostic::error(
                                2003,
                                format!(
                                    "المفتاح {} غير موجود في القاموس",
                                    format_value(&i, false, true)
                                ),
                            )
                            .with_span(index.span)
                            .into())
                        }
                    },
                    other => {
                        return Err(Diagnostic::error(
                            2007,
                            format!("لا يمكن الفهرسة في قيمة من نوع {}", other.type_name()),
                        )
                        .with_span(obj.span)
                        .into())
                    }
                }
            }
            ExprKind::Member { obj, name } => {
                let o = self.eval(obj, env)?;
                match o {
                    Value::Dict(d) => match dict_lookup(&d.borrow(), &Value::str(name.as_str())) {
                        Some(v) => v,
                        None => {
                            return Err(Diagnostic::error(
                                2003,
                                format!("لا يوجد عضو باسم «{name}»"),
                            )
                            .with_span(e.span)
                            .into())
                        }
                    },
                    other => {
                        return Err(Diagnostic::error(
                            2007,
                            format!("القيمة من نوع {} لا تملك أعضاء", other.type_name()),
                        )
                        .with_span(obj.span)
                        .into())
                    }
                }
            }
            ExprKind::Range { from, to } => {
                let a = self.eval(from, env)?;
                let b = self.eval(to, env)?;
                // المدى نصف مفتوح [من، إلى): حدٌّ عشري يُقرَّب للأعلى فيبقى
                // المدى محتويًا تمامًا على الأعداد الصحيحة ع حيث من <= ع < إلى.
                match (a.as_f64(), b.as_f64()) {
                    (Some(x), Some(y)) if x.is_finite() && y.is_finite() => {
                        Value::Range(x.ceil() as i64, y.ceil() as i64)
                    }
                    _ => {
                        return Err(Diagnostic::error(
                            2007,
                            format!(
                                "حدود المدى يجب أن تكون أعدادًا، لا {} و{}",
                                a.type_name(),
                                b.type_name()
                            ),
                        )
                        .with_span(e.span)
                        .into())
                    }
                }
            }
        })
    }

    pub fn call(&mut self, f: Value, args: Vec<Value>, span: Span) -> R<Value> {
        match f {
            Value::Builtin(b) => Ok((b.func)(self, args, span)?),
            Value::Func(func) => {
                if args.len() != func.params.len() {
                    return Err(Diagnostic::error(
                        1004,
                        format!(
                            "الدالة «{}» تتوقع {} من المعاملات لكنها تلقّت {}",
                            func.name,
                            func.params.len(),
                            args.len()
                        ),
                    )
                    .with_span(span)
                    .into());
                }
                self.depth += 1;
                if self.depth > MAX_DEPTH {
                    self.depth -= 1;
                    return Err(Diagnostic::error(
                        2004,
                        format!("تجاوز عمق الاستدعاء ({MAX_DEPTH}) في الدالة «{}»", func.name),
                    )
                    .with_span(span)
                    .into());
                }
                let scope = func.closure.child();
                for (p, a) in func.params.iter().zip(args) {
                    scope.define(p, a, false);
                }
                let result = match self.exec_block(&func.body, &scope) {
                    Ok(()) => Ok(Value::Null),
                    Err(Flow::Return(v)) => Ok(v),
                    Err(Flow::Break) | Err(Flow::Continue) => {
                        Err(Diagnostic::error(1007, "«توقف» أو «استمر» خارج حلقة")
                            .with_span(span)
                            .into())
                    }
                    Err(Flow::Err(d)) => Err(Flow::Err(d)),
                };
                self.depth -= 1;
                result
            }
            other => Err(Diagnostic::error(
                1005,
                format!("لا يمكن استدعاء قيمة من نوع {}", other.type_name()),
            )
            .with_span(span)
            .into()),
        }
    }

    fn binary(&mut self, op: BinOp, l: Value, r: Value, span: Span) -> R<Value> {
        use Value::*;
        let err = |code: u16, msg: String| -> Flow {
            Diagnostic::error(code, msg).with_span(span).into()
        };
        let undefined_op = || {
            err(
                1011,
                format!(
                    "العملية «{}» غير معرَّفة بين {} و{}",
                    op.symbol(),
                    l.type_name(),
                    r.type_name()
                ),
            )
        };
        Ok(match (op, &l, &r) {
            (BinOp::Eq, _, _) => Bool(l.equals(&r)),
            (BinOp::NotEq, _, _) => Bool(!l.equals(&r)),

            (BinOp::Add, Int(a), Int(b)) => a
                .checked_add(*b)
                .map(Int)
                .unwrap_or(Float(*a as f64 + *b as f64)),
            (BinOp::Sub, Int(a), Int(b)) => a
                .checked_sub(*b)
                .map(Int)
                .unwrap_or(Float(*a as f64 - *b as f64)),
            (BinOp::Mul, Int(a), Int(b)) => a
                .checked_mul(*b)
                .map(Int)
                .unwrap_or(Float(*a as f64 * *b as f64)),
            (BinOp::Add, Str(a), Str(b)) => Value::str(format!("{a}{b}")),
            (BinOp::Add, List(a), List(b)) => {
                let mut v = a.borrow().clone();
                v.extend(b.borrow().iter().cloned());
                Value::list(v)
            }
            (BinOp::Add, Str(_), Int(_) | Float(_)) | (BinOp::Add, Int(_) | Float(_), Str(_)) => {
                return Err(err(1003, "لا يمكن جمع نص مع عدد".into()))
            }
            (BinOp::Mul, Str(s), Int(n)) | (BinOp::Mul, Int(n), Str(s)) => {
                Value::str(s.repeat((*n).max(0) as usize))
            }

            (BinOp::Div, _, _) => {
                let (Some(a), Some(b)) = (l.as_f64(), r.as_f64()) else {
                    return Err(undefined_op());
                };
                if b == 0.0 {
                    return Err(err(2001, "قسمة على صفر".into()));
                }
                Float(a / b)
            }
            (BinOp::IntDiv, Int(a), Int(b)) => {
                if *b == 0 {
                    return Err(err(2001, "قسمة على صفر".into()));
                }
                Int((*a as f64 / *b as f64).floor() as i64)
            }
            (BinOp::Mod, Int(a), Int(b)) => {
                if *b == 0 {
                    return Err(err(2001, "باقي القسمة على صفر".into()));
                }
                Int(a.rem_euclid(*b))
            }
            (BinOp::IntDiv | BinOp::Mod, _, _) => {
                let (Some(a), Some(b)) = (l.as_f64(), r.as_f64()) else {
                    return Err(undefined_op());
                };
                if b == 0.0 {
                    return Err(err(2001, "قسمة على صفر".into()));
                }
                if op == BinOp::IntDiv {
                    Float((a / b).floor())
                } else {
                    Float(a.rem_euclid(b))
                }
            }
            (BinOp::Add | BinOp::Sub | BinOp::Mul, _, _) => {
                let (Some(a), Some(b)) = (l.as_f64(), r.as_f64()) else {
                    return Err(undefined_op());
                };
                Float(match op {
                    BinOp::Add => a + b,
                    BinOp::Sub => a - b,
                    _ => a * b,
                })
            }

            (BinOp::Lt | BinOp::Gt | BinOp::LtEq | BinOp::GtEq, _, _) => {
                let ord = match (&l, &r) {
                    (Str(a), Str(b)) => a.cmp(b),
                    _ => match (l.as_f64(), r.as_f64()) {
                        (Some(a), Some(b)) => {
                            a.partial_cmp(&b).unwrap_or(std::cmp::Ordering::Equal)
                        }
                        _ => {
                            return Err(err(
                                1008,
                                format!("لا يمكن المقارنة بين {} و{}", l.type_name(), r.type_name()),
                            ))
                        }
                    },
                };
                use std::cmp::Ordering::*;
                Bool(match op {
                    BinOp::Lt => ord == Less,
                    BinOp::Gt => ord == Greater,
                    BinOp::LtEq => ord != Greater,
                    _ => ord != Less,
                })
            }

            (BinOp::In, x, List(items)) => Bool(items.borrow().iter().any(|i| i.equals(x))),
            (BinOp::In, Str(a), Str(b)) => Bool(b.contains(&**a)),
            (BinOp::In, k, Dict(d)) => Bool(dict_lookup(&d.borrow(), k).is_some()),
            (BinOp::In, Int(i), Range(a, b)) => Bool(*a <= *i && *i < *b),
            (BinOp::In, _, _) => return Err(undefined_op()),
            (BinOp::And | BinOp::Or, _, _) => unreachable!("short-circuit handled in eval"),
        })
    }
}

fn logic_type_error(op: BinOp, v: &Value, span: Span) -> Flow {
    Diagnostic::error(
        1011,
        format!(
            "العملية «{}» تتطلب قيمتين منطقيتين، لكن أحد الطرفين من نوع {}",
            op.symbol(),
            v.type_name()
        ),
    )
    .with_span(span)
    .into()
}

pub(crate) fn list_index(i: &Value, len: usize, span: Span) -> Result<usize, Diagnostic> {
    match i {
        Value::Int(n) => {
            if *n < 0 || (*n as usize) >= len {
                Err(
                    Diagnostic::error(2002, format!("الفهرس {n} خارج الحدود (الطول {len})"))
                        .with_span(span),
                )
            } else {
                Ok(*n as usize)
            }
        }
        other => Err(Diagnostic::error(
            2007,
            format!("الفهرس يجب أن يكون عددًا صحيحًا، لا {}", other.type_name()),
        )
        .with_span(span)),
    }
}

enum Iter {
    Range(i64, i64),
    Items(std::vec::IntoIter<Value>),
}

impl Iter {
    fn new(v: Value, span: Span) -> Result<Iter, Diagnostic> {
        Ok(match v {
            Value::Range(a, b) => Iter::Range(a, b),
            Value::List(l) => Iter::Items(l.borrow().clone().into_iter()),
            Value::Str(s) => Iter::Items(
                s.chars()
                    .map(|c| Value::str(c.to_string()))
                    .collect::<Vec<_>>()
                    .into_iter(),
            ),
            Value::Dict(d) => Iter::Items(
                d.borrow()
                    .iter()
                    .map(|(k, _)| k.clone())
                    .collect::<Vec<_>>()
                    .into_iter(),
            ),
            other => {
                return Err(Diagnostic::error(
                    2007,
                    format!("لا يمكن التكرار على قيمة من نوع {}", other.type_name()),
                )
                .with_help("استخدم مدى مثل ١..١٠ أو قائمة أو نصًا.")
                .with_span(span))
            }
        })
    }
}

impl Iterator for Iter {
    type Item = Value;
    fn next(&mut self) -> Option<Value> {
        match self {
            Iter::Range(a, b) => {
                if a < b {
                    let v = *a;
                    *a += 1;
                    Some(Value::Int(v))
                } else {
                    None
                }
            }
            Iter::Items(it) => it.next(),
        }
    }
}

/// مسافة ليفنشتاين بين نصين (بالمحارف) لاقتراح الأسماء القريبة.
pub(crate) fn levenshtein(a: &str, b: &str) -> usize {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    let mut prev: Vec<usize> = (0..=b.len()).collect();
    let mut cur = vec![0; b.len() + 1];
    for (i, ca) in a.iter().enumerate() {
        cur[0] = i + 1;
        for (j, cb) in b.iter().enumerate() {
            let cost = if ca == cb { 0 } else { 1 };
            cur[j + 1] = (prev[j + 1] + 1).min(cur[j] + 1).min(prev[j] + cost);
        }
        std::mem::swap(&mut prev, &mut cur);
    }
    prev[b.len()]
}
