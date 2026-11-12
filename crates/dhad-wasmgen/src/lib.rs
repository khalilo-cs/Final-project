//! مولّد WebAssembly للغة ضاد.
//!
//! يترجم مجموعة فرعية عددية من اللغة مباشرة إلى وحدة `.wasm` ثنائية:
//! أعداد صحيحة (64-بت) وقيم منطقية، متغيرات وثوابت، عمليات حسابية ومنطقية
//! ومقارنات، «إذا/وإلا إذا/وإلا»، «طالما»، «لكل ... في مدى»، «توقف/استمر»،
//! دوال (مع الاستدعاء الذاتي)، والطباعة مع دمج النصوص.
//! ما سوى ذلك يُرفض بخطأ ضاد-4001 يشرح ما ليس مدعومًا بعد.
//!
//! الدلالات تطابق المفسر: القسمة الصحيحة «//» تقريب للأسفل، و«%» باقٍ غير سالب،
//! والقسمة على صفر تُوقف البرنامج بالخطأ ضاد-2001 عبر المضيف.
//!
//! واجهة المضيف (الوحدة "env"):
//! - `print_i64(i64)`، `print_bool(i32)`، `print_str(ptr: i32, len: i32)`، `print_newline()`
//! - `fail(code: i32)`: يُنهي التنفيذ بكود خطأ ضاد.
//!
//! الوحدة تصدّر `run()` و`memory`.

use dhad_diagnostics::{Diagnostic, Span};
use dhad_syntax::*;
use std::collections::HashMap;
use wasm_encoder::{
    BlockType, CodeSection, ConstExpr, DataSection, EntityType, ExportKind, ExportSection,
    Function, FunctionSection, GlobalSection, GlobalType, ImportSection, Instruction as I,
    MemorySection, MemoryType, Module, TypeSection, ValType,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum Ty {
    Int,
    Bool,
}

impl Ty {
    fn val(self) -> ValType {
        match self {
            Ty::Int => ValType::I64,
            Ty::Bool => ValType::I32,
        }
    }
    fn name(self) -> &'static str {
        match self {
            Ty::Int => "عدد_صحيح",
            Ty::Bool => "منطقي",
        }
    }
}

fn unsupported(what: &str, span: Span) -> Diagnostic {
    Diagnostic::error(4001, format!("{what} غير مدعوم بعد في مولّد WebAssembly"))
        .with_help("المدعوم: الأعداد الصحيحة والقيم المنطقية، الدوال، الشروط والحلقات على المدى، والطباعة. شغّل البرنامج بالمفسر لبقية اللغة.")
        .with_span(span)
}

fn type_error(msg: String, span: Span) -> Diagnostic {
    Diagnostic::error(4002, msg).with_span(span)
}

// فهارس الدوال المستوردة والمساعدة.
const F_PRINT_I64: u32 = 0;
const F_PRINT_BOOL: u32 = 1;
const F_PRINT_STR: u32 = 2;
const F_PRINT_NL: u32 = 3;
const F_FAIL: u32 = 4;
const F_FLOORDIV: u32 = 5;
const F_FLOORMOD: u32 = 6;
const F_ABS: u32 = 7;
const F_MAX: u32 = 8;
const F_MIN: u32 = 9;
const FIRST_USER_FN: u32 = 10;

struct FnSig {
    index: u32,
    params: usize,
    ret: Option<Ty>,
}

struct GlobalVar {
    index: u32,
    ty: Ty,
    is_const: bool,
}

/// إطار تحكم لحساب أعماق «br».
#[derive(Clone, Copy, PartialEq)]
enum Frame {
    Plain,
    LoopExit,
    LoopTop,
    LoopContinue,
}

struct FnCtx {
    locals: Vec<ValType>,
    n_params: u32,
    scopes: Vec<HashMap<String, (u32, Ty, bool)>>,
    frames: Vec<Frame>,
    in_function: bool,
    ret: Option<Ty>,
    code: Vec<I<'static>>,
}

impl FnCtx {
    fn new(params: &[(String, Span)], in_function: bool) -> FnCtx {
        let mut scope = HashMap::new();
        for (i, (p, _)) in params.iter().enumerate() {
            scope.insert(p.clone(), (i as u32, Ty::Int, false));
        }
        FnCtx {
            locals: Vec::new(),
            n_params: params.len() as u32,
            scopes: vec![scope],
            frames: Vec::new(),
            in_function,
            ret: None,
            code: Vec::new(),
        }
    }

    fn new_local(&mut self, ty: Ty) -> u32 {
        self.locals.push(ty.val());
        self.n_params + self.locals.len() as u32 - 1
    }

    fn lookup(&self, name: &str) -> Option<(u32, Ty, bool)> {
        self.scopes.iter().rev().find_map(|s| s.get(name).copied())
    }

    fn depth_to(&self, target: Frame) -> Option<u32> {
        self.frames
            .iter()
            .rev()
            .position(|f| *f == target)
            .map(|d| d as u32)
    }
}

struct Compiler<'p> {
    program: &'p Program,
    fns: HashMap<String, FnSig>,
    globals: HashMap<String, GlobalVar>,
    global_types: Vec<Ty>,
    data: Vec<u8>,
    strings: HashMap<String, (u32, u32)>,
    /// وضع الاستنتاج: لا يُبلَّغ عن أخطاء الأنواع الناتجة عن أنواع إرجاع لم تُعرف بعد.
    inferring: bool,
}

/// ناتج الترجمة: الوحدة الثنائية وصيغتها النصية (WAT) المكافئة.
pub struct Output {
    pub wasm: Vec<u8>,
    pub wat: String,
}

/// ترجمة نص مطبَّع إلى وحدة WebAssembly ثنائية.
pub fn compile(src: &str) -> Result<Vec<u8>, Diagnostic> {
    compile_full(src).map(|o| o.wasm)
}

/// ترجمة نص مطبَّع إلى وحدة ثنائية مع صيغتها النصية (WAT) للتعليم والتصحيح.
pub fn compile_full(src: &str) -> Result<Output, Diagnostic> {
    let program = parse(src)?;
    let mut c = Compiler {
        program: &program,
        fns: HashMap::new(),
        globals: HashMap::new(),
        global_types: Vec::new(),
        data: Vec::new(),
        strings: HashMap::new(),
        inferring: true,
    };
    c.collect_functions()?;
    // استنتاج أنواع الإرجاع بالتكرار حتى الاستقرار (يكفي لبرامج الاستدعاء المتبادل).
    for _ in 0..6 {
        let before: Vec<Option<Ty>> = c.fn_order().iter().map(|n| c.fns[n].ret).collect();
        c.reset_globals();
        let _ = c.compile_all();
        let after: Vec<Option<Ty>> = c.fn_order().iter().map(|n| c.fns[n].ret).collect();
        if before == after {
            break;
        }
    }
    c.inferring = false;
    c.reset_globals();
    let (funcs, main) = c.compile_all()?;
    Ok(c.emit(funcs, main))
}

impl Compiler<'_> {
    fn fn_order(&self) -> Vec<String> {
        let mut v: Vec<(&String, &FnSig)> = self.fns.iter().collect();
        v.sort_by_key(|(_, s)| s.index);
        v.into_iter().map(|(n, _)| n.clone()).collect()
    }

    fn reset_globals(&mut self) {
        self.globals.clear();
        self.global_types.clear();
    }

    fn collect_functions(&mut self) -> Result<(), Diagnostic> {
        let mut next = FIRST_USER_FN;
        for s in &self.program.stmts {
            if let StmtKind::FnDecl { name, params, .. } = &s.kind {
                self.fns.insert(
                    name.clone(),
                    FnSig {
                        index: next,
                        params: params.len(),
                        ret: None,
                    },
                );
                next += 1;
            }
        }
        Ok(())
    }

    fn compile_all(&mut self) -> Result<(Vec<FnCtx>, FnCtx), Diagnostic> {
        // المتغيرات العامة أولًا (بالترتيب)، لأن الدوال قد تقرؤها.
        let mut main = FnCtx::new(&[], false);
        let mut funcs = Vec::new();
        let program = self.program;
        for s in &program.stmts {
            self.stmt(s, &mut main, true)?;
        }
        main.code.push(I::End);
        for s in &program.stmts {
            if let StmtKind::FnDecl {
                name, params, body, ..
            } = &s.kind
            {
                let mut f = FnCtx::new(params, true);
                for st in &body.stmts {
                    self.stmt(st, &mut f, false)?;
                }
                let ret = f.ret.unwrap_or(Ty::Int);
                f.code.push(match ret {
                    Ty::Int => I::I64Const(0),
                    Ty::Bool => I::I32Const(0),
                });
                f.code.push(I::End);
                self.fns.get_mut(name).unwrap().ret = Some(ret);
                funcs.push(f);
            }
        }
        Ok((funcs, main))
    }

    fn intern(&mut self, s: &str) -> (u32, u32) {
        if let Some(&v) = self.strings.get(s) {
            return v;
        }
        let off = self.data.len() as u32;
        self.data.extend_from_slice(s.as_bytes());
        let v = (off, s.len() as u32);
        self.strings.insert(s.to_string(), v);
        v
    }

    fn block(&mut self, b: &Block, f: &mut FnCtx) -> Result<(), Diagnostic> {
        f.scopes.push(HashMap::new());
        for s in &b.stmts {
            self.stmt(s, f, false)?;
        }
        f.scopes.pop();
        Ok(())
    }

    fn stmt(&mut self, s: &Stmt, f: &mut FnCtx, top: bool) -> Result<(), Diagnostic> {
        match &s.kind {
            StmtKind::Let {
                name,
                value,
                is_const,
                ..
            } => {
                let ty = self.expr(value, f)?;
                if top {
                    let index = self.global_types.len() as u32;
                    self.global_types.push(ty);
                    self.globals.insert(
                        name.clone(),
                        GlobalVar {
                            index,
                            ty,
                            is_const: *is_const,
                        },
                    );
                    f.code.push(I::GlobalSet(index));
                } else {
                    let idx = f.new_local(ty);
                    f.scopes
                        .last_mut()
                        .unwrap()
                        .insert(name.clone(), (idx, ty, *is_const));
                    f.code.push(I::LocalSet(idx));
                }
            }
            StmtKind::Assign { target, value } => {
                let ExprKind::Ident(name) = &target.kind else {
                    return Err(unsupported(
                        "الإسناد إلى عناصر القوائم والقواميس",
                        target.span,
                    ));
                };
                let vty = self.expr(value, f)?;
                let (set, ty, is_const) = if let Some((i, ty, c)) = f.lookup(name) {
                    (I::LocalSet(i), ty, c)
                } else if let Some(g) = self.globals.get(name) {
                    (I::GlobalSet(g.index), g.ty, g.is_const)
                } else {
                    return Err(
                        Diagnostic::error(1001, format!("المتغير «{name}» غير معرَّف"))
                            .with_span(target.span),
                    );
                };
                if is_const {
                    return Err(Diagnostic::error(
                        1002,
                        format!("«{name}» ثابت ولا يمكن تغيير قيمته"),
                    )
                    .with_span(target.span));
                }
                self.expect(ty, vty, value.span, &format!("قيمة «{name}»"))?;
                f.code.push(set);
            }
            StmtKind::If {
                cond,
                then,
                elifs,
                otherwise,
            } => {
                self.cond(cond, f)?;
                f.code.push(I::If(BlockType::Empty));
                f.frames.push(Frame::Plain);
                self.block(then, f)?;
                let mut opened = 1;
                for (c, b) in elifs {
                    f.code.push(I::Else);
                    self.cond(c, f)?;
                    f.code.push(I::If(BlockType::Empty));
                    f.frames.push(Frame::Plain);
                    self.block(b, f)?;
                    opened += 1;
                }
                if let Some(b) = otherwise {
                    f.code.push(I::Else);
                    self.block(b, f)?;
                }
                for _ in 0..opened {
                    f.code.push(I::End);
                    f.frames.pop();
                }
            }
            StmtKind::While { cond, body } => {
                f.code.push(I::Block(BlockType::Empty));
                f.frames.push(Frame::LoopExit);
                f.code.push(I::Loop(BlockType::Empty));
                f.frames.push(Frame::LoopTop);
                self.cond(cond, f)?;
                f.code.push(I::I32Eqz);
                f.code.push(I::BrIf(1));
                f.code.push(I::Block(BlockType::Empty));
                f.frames.push(Frame::LoopContinue);
                self.block(body, f)?;
                f.code.push(I::End);
                f.frames.pop();
                f.code.push(I::Br(0));
                f.code.push(I::End);
                f.frames.pop();
                f.code.push(I::End);
                f.frames.pop();
            }
            StmtKind::For {
                var, iter, body, ..
            } => {
                let (from, to) = match &iter.kind {
                    ExprKind::Range { from, to } => (from.as_ref().clone(), to.as_ref().clone()),
                    ExprKind::Call { callee, args } if matches!(&callee.kind, ExprKind::Ident(n) if n == "مدى") => {
                        match args.as_slice() {
                            [b] => (
                                Expr {
                                    kind: ExprKind::Int(0),
                                    span: iter.span,
                                },
                                b.clone(),
                            ),
                            [a, b] => (a.clone(), b.clone()),
                            _ => return Err(unsupported("هذا الشكل من «مدى»", iter.span)),
                        }
                    }
                    _ => {
                        return Err(unsupported(
                            "التكرار على غير المدى (قوائم ونصوص)",
                            iter.span,
                        ))
                    }
                };
                let t = self.expr(&from, f)?;
                self.expect(Ty::Int, t, from.span, "بداية المدى")?;
                let counter = f.new_local(Ty::Int);
                f.code.push(I::LocalSet(counter));
                let t = self.expr(&to, f)?;
                self.expect(Ty::Int, t, to.span, "نهاية المدى")?;
                let end = f.new_local(Ty::Int);
                f.code.push(I::LocalSet(end));
                f.scopes
                    .push(HashMap::from([(var.clone(), (counter, Ty::Int, false))]));
                f.code.push(I::Block(BlockType::Empty));
                f.frames.push(Frame::LoopExit);
                f.code.push(I::Loop(BlockType::Empty));
                f.frames.push(Frame::LoopTop);
                f.code.extend([
                    I::LocalGet(counter),
                    I::LocalGet(end),
                    I::I64GeS,
                    I::BrIf(1),
                ]);
                f.code.push(I::Block(BlockType::Empty));
                f.frames.push(Frame::LoopContinue);
                self.block(body, f)?;
                f.code.push(I::End);
                f.frames.pop();
                f.code.extend([
                    I::LocalGet(counter),
                    I::I64Const(1),
                    I::I64Add,
                    I::LocalSet(counter),
                    I::Br(0),
                ]);
                f.code.push(I::End);
                f.frames.pop();
                f.code.push(I::End);
                f.frames.pop();
                f.scopes.pop();
            }
            StmtKind::FnDecl { .. } if top => {}
            StmtKind::FnDecl { .. } => {
                return Err(unsupported("تعريف دالة داخل دالة أو كتلة", s.span));
            }
            StmtKind::Return(e) => {
                if !f.in_function {
                    return Err(Diagnostic::error(1006, "«أرجع» خارج دالة").with_span(s.span));
                }
                let ty = match e {
                    Some(e) => self.expr(e, f)?,
                    None => {
                        f.code.push(I::I64Const(0));
                        Ty::Int
                    }
                };
                match f.ret {
                    None => f.ret = Some(ty),
                    Some(r) => self.expect(r, ty, s.span, "القيمة المُرجَعة")?,
                }
                f.code.push(I::Return);
            }
            StmtKind::Break | StmtKind::Continue => {
                let target = if matches!(s.kind, StmtKind::Break) {
                    Frame::LoopExit
                } else {
                    Frame::LoopContinue
                };
                match f.depth_to(target) {
                    Some(d) => f.code.push(I::Br(d)),
                    None => {
                        return Err(Diagnostic::error(1007, "«توقف» أو «استمر» خارج حلقة")
                            .with_span(s.span))
                    }
                }
            }
            StmtKind::Import { .. } => {}
            StmtKind::Test { .. } => return Err(unsupported("كتل «اختبر»", s.span)),
            StmtKind::Expr(e) => {
                if let ExprKind::Call { callee, args } = &e.kind {
                    if matches!(&callee.kind, ExprKind::Ident(n) if n == "اطبع") {
                        return self.print(args, f);
                    }
                }
                self.expr(e, f)?;
                f.code.push(I::Drop);
            }
        }
        Ok(())
    }

    fn print(&mut self, args: &[Expr], f: &mut FnCtx) -> Result<(), Diagnostic> {
        for (i, a) in args.iter().enumerate() {
            if i > 0 {
                let (p, l) = self.intern(" ");
                f.code.extend([
                    I::I32Const(p as i32),
                    I::I32Const(l as i32),
                    I::Call(F_PRINT_STR),
                ]);
            }
            if let ExprKind::Str(segs) = &a.kind {
                for seg in segs {
                    match seg {
                        StrSeg::Text(t) if t.is_empty() => {}
                        StrSeg::Text(t) => {
                            let (p, l) = self.intern(t);
                            f.code.extend([
                                I::I32Const(p as i32),
                                I::I32Const(l as i32),
                                I::Call(F_PRINT_STR),
                            ]);
                        }
                        StrSeg::Expr(x) => self.print_value(x, f)?,
                    }
                }
            } else {
                self.print_value(a, f)?;
            }
        }
        f.code.push(I::Call(F_PRINT_NL));
        Ok(())
    }

    fn print_value(&mut self, e: &Expr, f: &mut FnCtx) -> Result<(), Diagnostic> {
        match self.expr(e, f)? {
            Ty::Int => f.code.push(I::Call(F_PRINT_I64)),
            Ty::Bool => f.code.push(I::Call(F_PRINT_BOOL)),
        }
        Ok(())
    }

    fn expect(&self, want: Ty, got: Ty, span: Span, what: &str) -> Result<(), Diagnostic> {
        if want != got && !self.inferring {
            return Err(type_error(
                format!("{what} يجب أن تكون {} لكنها {}", want.name(), got.name()),
                span,
            ));
        }
        Ok(())
    }

    fn cond(&mut self, e: &Expr, f: &mut FnCtx) -> Result<(), Diagnostic> {
        let t = self.expr(e, f)?;
        if t != Ty::Bool && !self.inferring {
            return Err(Diagnostic::error(
                1010,
                format!("الشرط يجب أن يكون صحيح أو خطأ، لكنه {}", t.name()),
            )
            .with_span(e.span));
        }
        Ok(())
    }

    fn expr(&mut self, e: &Expr, f: &mut FnCtx) -> Result<Ty, Diagnostic> {
        Ok(match &e.kind {
            ExprKind::Int(n) => {
                f.code.push(I::I64Const(*n));
                Ty::Int
            }
            ExprKind::Bool(b) => {
                f.code.push(I::I32Const(*b as i32));
                Ty::Bool
            }
            ExprKind::Float(_) => return Err(unsupported("الأعداد العشرية", e.span)),
            ExprKind::Str(_) => return Err(unsupported("النصوص خارج «اطبع»", e.span)),
            ExprKind::Null => return Err(unsupported("القيمة «عدم»", e.span)),
            ExprKind::List(_) | ExprKind::Dict(_) | ExprKind::Index { .. } => {
                return Err(unsupported("القوائم والقواميس", e.span))
            }
            ExprKind::Member { .. } => return Err(unsupported("الوحدات وأعضاؤها", e.span)),
            ExprKind::Range { .. } => return Err(unsupported("المدى خارج «لكل»", e.span)),
            ExprKind::Ident(name) => {
                if let Some((i, ty, _)) = f.lookup(name) {
                    f.code.push(I::LocalGet(i));
                    ty
                } else if let Some(g) = self.globals.get(name) {
                    f.code.push(I::GlobalGet(g.index));
                    g.ty
                } else if self.inferring && f.in_function {
                    // متغير عام يُعرَّف بعد الدالة: نوعه يُعرف في المرور التالي.
                    f.code.push(I::I64Const(0));
                    Ty::Int
                } else if self.fns.contains_key(name) {
                    return Err(unsupported("استخدام الدوال كقيم", e.span));
                } else {
                    return Err(
                        Diagnostic::error(1001, format!("المتغير «{name}» غير معرَّف"))
                            .with_span(e.span),
                    );
                }
            }
            ExprKind::Unary { op, expr } => match op {
                UnOp::Neg => {
                    f.code.push(I::I64Const(0));
                    let t = self.expr(expr, f)?;
                    self.expect(Ty::Int, t, expr.span, "معامل السالب")?;
                    f.code.push(I::I64Sub);
                    Ty::Int
                }
                UnOp::Not => {
                    let t = self.expr(expr, f)?;
                    self.expect(Ty::Bool, t, expr.span, "معامل «ليس»")?;
                    f.code.push(I::I32Eqz);
                    Ty::Bool
                }
            },
            ExprKind::Binary { op, left, right } => self.binary(*op, left, right, e.span, f)?,
            ExprKind::Call { callee, args } => {
                let ExprKind::Ident(name) = &callee.kind else {
                    return Err(unsupported("استدعاء غير مباشر", callee.span));
                };
                let builtin = match name.as_str() {
                    "مطلق" => Some((F_ABS, 1)),
                    "أكبر" => Some((F_MAX, 2)),
                    "أصغر" => Some((F_MIN, 2)),
                    _ => None,
                };
                let (index, arity, ret) = if let Some((idx, n)) = builtin {
                    (idx, n, Ty::Int)
                } else if let Some(sig) = self.fns.get(name) {
                    (sig.index, sig.params, sig.ret.unwrap_or(Ty::Int))
                } else if name == "اطبع" {
                    return Err(unsupported("استخدام «اطبع» داخل تعبير", e.span));
                } else if dhad_syntax::Kw::from_ident(name).is_none() && f.lookup(name).is_none() {
                    return Err(unsupported(&format!("الدالة «{name}»"), callee.span));
                } else {
                    return Err(unsupported("استدعاء متغير", callee.span));
                };
                if args.len() != arity {
                    return Err(Diagnostic::error(
                        1004,
                        format!(
                            "الدالة «{name}» تتوقع {arity} من المعاملات لكنها تلقّت {}",
                            args.len()
                        ),
                    )
                    .with_span(e.span));
                }
                for a in args {
                    let t = self.expr(a, f)?;
                    self.expect(Ty::Int, t, a.span, "معاملات الدوال في مولّد WebAssembly")?;
                }
                f.code.push(I::Call(index));
                ret
            }
        })
    }

    fn binary(
        &mut self,
        op: BinOp,
        left: &Expr,
        right: &Expr,
        span: Span,
        f: &mut FnCtx,
    ) -> Result<Ty, Diagnostic> {
        if matches!(op, BinOp::And | BinOp::Or) {
            let lt = self.expr(left, f)?;
            self.expect(Ty::Bool, lt, left.span, &format!("طرف «{}»", op.symbol()))?;
            f.code.push(I::If(BlockType::Result(ValType::I32)));
            f.frames.push(Frame::Plain);
            if op == BinOp::And {
                let rt = self.expr(right, f)?;
                self.expect(Ty::Bool, rt, right.span, "طرف «و»")?;
                f.code.push(I::Else);
                f.code.push(I::I32Const(0));
            } else {
                f.code.push(I::I32Const(1));
                f.code.push(I::Else);
                let rt = self.expr(right, f)?;
                self.expect(Ty::Bool, rt, right.span, "طرف «أو»")?;
            }
            f.code.push(I::End);
            f.frames.pop();
            return Ok(Ty::Bool);
        }
        let lt = self.expr(left, f)?;
        let rt = self.expr(right, f)?;
        if matches!(op, BinOp::Eq | BinOp::NotEq) {
            if lt != rt && !self.inferring {
                return Err(type_error(
                    format!("لا يمكن مقارنة {} بـ{}", lt.name(), rt.name()),
                    span,
                ));
            }
            f.code.push(match (op, lt) {
                (BinOp::Eq, Ty::Int) => I::I64Eq,
                (BinOp::NotEq, Ty::Int) => I::I64Ne,
                (BinOp::Eq, Ty::Bool) => I::I32Eq,
                _ => I::I32Ne,
            });
            return Ok(Ty::Bool);
        }
        if op == BinOp::Div {
            return Err(unsupported(
                "القسمة العشرية «/» (استخدم القسمة الصحيحة «//»)",
                span,
            ));
        }
        if op == BinOp::In {
            return Err(unsupported("العملية «في»", span));
        }
        self.expect(Ty::Int, lt, left.span, &format!("طرف «{}»", op.symbol()))?;
        self.expect(Ty::Int, rt, right.span, &format!("طرف «{}»", op.symbol()))?;
        let (ins, ty) = match op {
            BinOp::Add => (I::I64Add, Ty::Int),
            BinOp::Sub => (I::I64Sub, Ty::Int),
            BinOp::Mul => (I::I64Mul, Ty::Int),
            BinOp::IntDiv => (I::Call(F_FLOORDIV), Ty::Int),
            BinOp::Mod => (I::Call(F_FLOORMOD), Ty::Int),
            BinOp::Lt => (I::I64LtS, Ty::Bool),
            BinOp::Gt => (I::I64GtS, Ty::Bool),
            BinOp::LtEq => (I::I64LeS, Ty::Bool),
            BinOp::GtEq => (I::I64GeS, Ty::Bool),
            _ => unreachable!(),
        };
        f.code.push(ins);
        Ok(ty)
    }

    fn emit(&mut self, funcs: Vec<FnCtx>, main: FnCtx) -> Output {
        let mut types = TypeSection::new();
        // 0: (i64)->()  1: (i32)->()  2: (i32,i32)->()  3: ()->()
        // 4: (i64,i64)->i64  5: (i64)->i64
        types.ty().function([ValType::I64], []);
        types.ty().function([ValType::I32], []);
        types.ty().function([ValType::I32, ValType::I32], []);
        types.ty().function([], []);
        types
            .ty()
            .function([ValType::I64, ValType::I64], [ValType::I64]);
        types.ty().function([ValType::I64], [ValType::I64]);
        let mut sig_types: HashMap<(usize, Ty), u32> = HashMap::new();
        let mut next_type = 6;
        let order = self.fn_order();
        for name in &order {
            let sig = &self.fns[name];
            let key = (sig.params, sig.ret.unwrap_or(Ty::Int));
            if let std::collections::hash_map::Entry::Vacant(v) = sig_types.entry(key) {
                types
                    .ty()
                    .function(vec![ValType::I64; key.0], [key.1.val()]);
                v.insert(next_type);
                next_type += 1;
            }
        }

        let mut imports = ImportSection::new();
        imports.import("env", "print_i64", EntityType::Function(0));
        imports.import("env", "print_bool", EntityType::Function(1));
        imports.import("env", "print_str", EntityType::Function(2));
        imports.import("env", "print_newline", EntityType::Function(3));
        imports.import("env", "fail", EntityType::Function(1));

        let mut functions = FunctionSection::new();
        functions.function(4); // floordiv
        functions.function(4); // floormod
        functions.function(5); // abs
        functions.function(4); // max
        functions.function(4); // min
        for name in &order {
            let sig = &self.fns[name];
            functions.function(sig_types[&(sig.params, sig.ret.unwrap_or(Ty::Int))]);
        }
        functions.function(3); // run
        let run_index = FIRST_USER_FN + order.len() as u32;

        let mut memory = MemorySection::new();
        let pages = (self.data.len() as u64 / 65536) + 1;
        memory.memory(MemoryType {
            minimum: pages,
            maximum: None,
            memory64: false,
            shared: false,
            page_size_log2: None,
        });

        let mut globals = GlobalSection::new();
        for ty in &self.global_types {
            let init = match ty {
                Ty::Int => ConstExpr::i64_const(0),
                Ty::Bool => ConstExpr::i32_const(0),
            };
            globals.global(
                GlobalType {
                    val_type: ty.val(),
                    mutable: true,
                    shared: false,
                },
                &init,
            );
        }

        let mut exports = ExportSection::new();
        exports.export("memory", ExportKind::Memory, 0);
        exports.export("run", ExportKind::Func, run_index);

        // الدوال المساعدة ثم دوال البرنامج بترتيب ظهورها (وهو ترتيب فهارسها) ثم run.
        let mut bodies: Vec<Body> = helpers();
        for (fc, name) in funcs.into_iter().zip(order.iter()) {
            let sig = &self.fns[name];
            bodies.push(Body {
                id: format!("$f{}", sig.index - FIRST_USER_FN),
                comment: format!("دالة {name}"),
                params: vec![ValType::I64; sig.params],
                result: Some(sig.ret.unwrap_or(Ty::Int).val()),
                locals: fc.locals,
                code: fc.code,
            });
        }
        bodies.push(Body {
            id: "$run".into(),
            comment: "المستوى الأعلى من البرنامج".into(),
            params: vec![],
            result: None,
            locals: main.locals,
            code: main.code,
        });
        let mut code = CodeSection::new();
        for b in &bodies {
            let mut func = Function::new_with_locals_types(b.locals.clone());
            for ins in &b.code {
                func.instruction(ins);
            }
            code.function(&func);
        }
        let wat = self.wat(&bodies);

        let mut data = DataSection::new();
        if !self.data.is_empty() {
            data.active(0, &ConstExpr::i32_const(0), self.data.iter().copied());
        }

        let mut module = Module::new();
        module
            .section(&types)
            .section(&imports)
            .section(&functions)
            .section(&memory)
            .section(&globals)
            .section(&exports)
            .section(&code)
            .section(&data);
        Output {
            wasm: module.finish(),
            wat,
        }
    }

    fn wat(&self, bodies: &[Body]) -> String {
        let mut names: Vec<String> = [
            "$print_i64",
            "$print_bool",
            "$print_str",
            "$print_newline",
            "$fail",
        ]
        .iter()
        .map(|s| s.to_string())
        .collect();
        names.extend(bodies.iter().map(|b| b.id.clone()));
        let mut w = String::from(";; وحدة WebAssembly ولّدها مترجم ضاد\n(module\n");
        w.push_str("  (import \"env\" \"print_i64\" (func $print_i64 (param i64)))\n");
        w.push_str("  (import \"env\" \"print_bool\" (func $print_bool (param i32)))\n");
        w.push_str("  (import \"env\" \"print_str\" (func $print_str (param i32 i32)))\n");
        w.push_str("  (import \"env\" \"print_newline\" (func $print_newline))\n");
        w.push_str("  (import \"env\" \"fail\" (func $fail (param i32)))\n");
        let pages = (self.data.len() as u64 / 65536) + 1;
        w.push_str(&format!("  (memory (export \"memory\") {pages})\n"));
        let names_by_index: HashMap<u32, &String> =
            self.globals.iter().map(|(n, g)| (g.index, n)).collect();
        for (i, ty) in self.global_types.iter().enumerate() {
            let t = val_name(ty.val());
            let label = names_by_index
                .get(&(i as u32))
                .map(|n| format!("  ;; {n}"))
                .unwrap_or_default();
            w.push_str(&format!(
                "  (global $g{i} (mut {t}) ({t}.const 0)){label}\n"
            ));
        }
        for b in bodies {
            w.push_str(&format!("\n  ;; {}\n  (func {}", b.comment, b.id));
            if b.id == "$run" {
                w.push_str(" (export \"run\")");
            }
            for p in &b.params {
                w.push_str(&format!(" (param {})", val_name(*p)));
            }
            if let Some(r) = b.result {
                w.push_str(&format!(" (result {})", val_name(r)));
            }
            for l in &b.locals {
                w.push_str(&format!(" (local {})", val_name(*l)));
            }
            w.push('\n');
            let mut depth = 2usize;
            let last = b.code.len().saturating_sub(1);
            for (k, ins) in b.code.iter().enumerate() {
                if k == last {
                    break; // «end» الختامية تُكتب كقوس الإغلاق.
                }
                if matches!(ins, I::End | I::Else) {
                    depth = depth.saturating_sub(1);
                }
                w.push_str(&"  ".repeat(depth));
                w.push_str(&ins_wat(ins, &names));
                w.push('\n');
                if matches!(ins, I::Block(_) | I::Loop(_) | I::If(_) | I::Else) {
                    depth += 1;
                }
            }
            w.push_str("  )\n");
        }
        if !self.data.is_empty() {
            w.push_str("\n  (data (i32.const 0) \"");
            for ch in String::from_utf8_lossy(&self.data).chars() {
                match ch {
                    '"' => w.push_str("\\\""),
                    '\\' => w.push_str("\\\\"),
                    c if (c as u32) < 0x20 => w.push_str(&format!("\\{:02x}", c as u32)),
                    c => w.push(c),
                }
            }
            w.push_str("\")\n");
        }
        w.push_str(")\n");
        w
    }
}

struct Body {
    id: String,
    comment: String,
    params: Vec<ValType>,
    result: Option<ValType>,
    locals: Vec<ValType>,
    code: Vec<I<'static>>,
}

fn val_name(v: ValType) -> &'static str {
    match v {
        ValType::I32 => "i32",
        ValType::I64 => "i64",
        ValType::F32 => "f32",
        ValType::F64 => "f64",
        _ => "?",
    }
}

fn block_wat(kw: &str, bt: &BlockType) -> String {
    match bt {
        BlockType::Result(v) => format!("{kw} (result {})", val_name(*v)),
        _ => kw.to_string(),
    }
}

/// تمثيل نصي لتعليمة من المجموعة التي يولّدها المترجم.
fn ins_wat(i: &I, names: &[String]) -> String {
    match i {
        I::I64Const(n) => format!("i64.const {n}"),
        I::I32Const(n) => format!("i32.const {n}"),
        I::LocalGet(n) => format!("local.get {n}"),
        I::LocalSet(n) => format!("local.set {n}"),
        I::LocalTee(n) => format!("local.tee {n}"),
        I::GlobalGet(n) => format!("global.get $g{n}"),
        I::GlobalSet(n) => format!("global.set $g{n}"),
        I::Call(n) => format!(
            "call {}",
            names.get(*n as usize).map(String::as_str).unwrap_or("?")
        ),
        I::Br(n) => format!("br {n}"),
        I::BrIf(n) => format!("br_if {n}"),
        I::Block(bt) => block_wat("block", bt),
        I::Loop(bt) => block_wat("loop", bt),
        I::If(bt) => block_wat("if", bt),
        I::Else => "else".into(),
        I::End => "end".into(),
        I::Return => "return".into(),
        I::Drop => "drop".into(),
        I::Unreachable => "unreachable".into(),
        I::Select => "select".into(),
        I::I32Eqz => "i32.eqz".into(),
        I::I32Eq => "i32.eq".into(),
        I::I32Ne => "i32.ne".into(),
        I::I32And => "i32.and".into(),
        I::I64Eqz => "i64.eqz".into(),
        I::I64Eq => "i64.eq".into(),
        I::I64Ne => "i64.ne".into(),
        I::I64LtS => "i64.lt_s".into(),
        I::I64GtS => "i64.gt_s".into(),
        I::I64LeS => "i64.le_s".into(),
        I::I64GeS => "i64.ge_s".into(),
        I::I64Add => "i64.add".into(),
        I::I64Sub => "i64.sub".into(),
        I::I64Mul => "i64.mul".into(),
        I::I64DivS => "i64.div_s".into(),
        I::I64RemS => "i64.rem_s".into(),
        I::I64Xor => "i64.xor".into(),
        I::I64ExtendI32U => "i64.extend_i32_u".into(),
        other => format!(";; {other:?}"),
    }
}

/// الدوال المساعدة: قسمة صحيحة بتقريب للأسفل، باقٍ غير سالب، مطلق، أكبر، أصغر.
fn helpers() -> Vec<Body> {
    let check_zero = [
        I::LocalGet(1),
        I::I64Eqz,
        I::If(BlockType::Empty),
        I::I32Const(2001),
        I::Call(F_FAIL),
        I::Unreachable,
        I::End,
    ];
    let bin = |id: &str, comment: &str, locals: Vec<ValType>, code: Vec<I<'static>>| Body {
        id: id.into(),
        comment: comment.into(),
        params: vec![ValType::I64, ValType::I64],
        result: Some(ValType::I64),
        locals,
        code,
    };

    // q = a / b ؛ إن كان الباقي غير صفري وإشارته تخالف إشارة b فـ q - 1.
    let mut fd = check_zero.to_vec();
    fd.extend([
        I::LocalGet(0),
        I::LocalGet(1),
        I::I64DivS,
        I::LocalGet(0),
        I::LocalGet(1),
        I::I64RemS,
        I::LocalTee(2),
        I::I64Const(0),
        I::I64Ne,
        I::LocalGet(2),
        I::LocalGet(1),
        I::I64Xor,
        I::I64Const(0),
        I::I64LtS,
        I::I32And,
        I::I64ExtendI32U,
        I::I64Sub,
        I::End,
    ]);

    // r = a % b ؛ إن كان r < 0 فـ r + |b|  (باقٍ غير سالب كما في المفسر).
    let mut fm = check_zero.to_vec();
    fm.extend([
        I::LocalGet(0),
        I::LocalGet(1),
        I::I64RemS,
        I::LocalTee(2),
        I::I64Const(0),
        I::I64LtS,
        I::If(BlockType::Result(ValType::I64)),
        I::LocalGet(2),
        I::LocalGet(1),
        I::Call(F_ABS),
        I::I64Add,
        I::Else,
        I::LocalGet(2),
        I::End,
        I::End,
    ]);

    let abs = Body {
        id: "$abs".into(),
        comment: "مساعد: مطلق".into(),
        params: vec![ValType::I64],
        result: Some(ValType::I64),
        locals: vec![],
        code: vec![
            I::I64Const(0),
            I::LocalGet(0),
            I::I64Sub,
            I::LocalGet(0),
            I::LocalGet(0),
            I::I64Const(0),
            I::I64LtS,
            I::Select,
            I::End,
        ],
    };
    let minmax = |cmp: I<'static>| {
        vec![
            I::LocalGet(0),
            I::LocalGet(1),
            I::LocalGet(0),
            I::LocalGet(1),
            cmp,
            I::Select,
            I::End,
        ]
    };
    vec![
        bin(
            "$floordiv",
            "مساعد: القسمة الصحيحة «//» بتقريب للأسفل",
            vec![ValType::I64],
            fd,
        ),
        bin(
            "$floormod",
            "مساعد: باقي القسمة «%» غير السالب",
            vec![ValType::I64],
            fm,
        ),
        abs,
        bin("$max", "مساعد: أكبر", vec![], minmax(I::I64GtS)),
        bin("$min", "مساعد: أصغر", vec![], minmax(I::I64LtS)),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    /// يترجم ويتحقق: الوحدة صالحة، وصيغتها النصية تُجمَّع بالمجمّع المرجعي إلى وحدة صالحة
    /// بالحجم نفسه تمامًا (أي أن WAT المعروض يصف الوحدة الحقيقية).
    fn ok(src: &str) -> Output {
        let out = compile_full(&normalize_source(src)).unwrap_or_else(|e| panic!("{e}"));
        wasmparser::Validator::new()
            .validate_all(&out.wasm)
            .unwrap_or_else(|e| panic!("وحدة غير صالحة: {e}\n{}", out.wat));
        let assembled =
            wat::parse_str(&out.wat).unwrap_or_else(|e| panic!("WAT غير صالح: {e}\n{}", out.wat));
        wasmparser::Validator::new()
            .validate_all(&assembled)
            .unwrap_or_else(|e| panic!("WAT المجمَّع غير صالح: {e}"));
        assert_eq!(
            summary(&assembled),
            summary(&out.wasm),
            "WAT لا يطابق الوحدة\n{}",
            out.wat
        );
        out
    }

    /// ملخص بنيوي للوحدة (دون الأقسام المخصصة كأسماء التصحيح): الاستيرادات، الأنواع
    /// الفعلية لكل دالة، المتغيرات العامة، التصديرات، البيانات، وكل تعليمة في كل دالة.
    fn summary(wasm: &[u8]) -> Vec<String> {
        use wasmparser::{Parser, Payload::*};
        let mut types = Vec::new();
        let mut out = Vec::new();
        for payload in Parser::new(0).parse_all(wasm) {
            match payload.unwrap() {
                TypeSection(r) => {
                    for t in r.into_iter_err_on_gc_types() {
                        types.push(format!("{:?}", t.unwrap()));
                    }
                }
                ImportSection(r) => {
                    for i in r {
                        let i = i.unwrap();
                        // نتجاهل إزاحة البايت في التمثيل النصي، فهي تختلف بين المرمِّزَين.
                        let text = format!("{i:?}");
                        out.push(format!(
                            "import {}",
                            text.split_once(", ").map(|x| x.1).unwrap_or(&text)
                        ));
                    }
                }
                FunctionSection(r) => {
                    for f in r {
                        out.push(format!("func {}", types[f.unwrap() as usize]));
                    }
                }
                GlobalSection(r) => {
                    for g in r {
                        out.push(format!("global {:?}", g.unwrap().ty));
                    }
                }
                ExportSection(r) => {
                    for e in r {
                        let e = e.unwrap();
                        out.push(format!("export {} {:?} {}", e.name, e.kind, e.index));
                    }
                }
                DataSection(r) => {
                    for d in r {
                        out.push(format!("data {:?}", d.unwrap().data));
                    }
                }
                CodeSectionEntry(body) => {
                    let mut locals = Vec::new();
                    for l in body.get_locals_reader().unwrap() {
                        let (n, t) = l.unwrap();
                        locals.extend(std::iter::repeat_n(format!("{t:?}"), n as usize));
                    }
                    out.push(format!("locals {locals:?}"));
                    let mut ops = body.get_operators_reader().unwrap();
                    while !ops.eof() {
                        out.push(format!("{:?}", ops.read().unwrap()));
                    }
                }
                _ => {}
            }
        }
        out
    }

    fn err(src: &str) -> u16 {
        compile(&normalize_source(src)).unwrap_err().code
    }

    #[test]
    fn compiles_valid_modules() {
        ok("اطبع(١ + ٢ * ٣)");
        ok("دالة فيب(ن) {\n إذا ن < ٢ { أرجع ن }\n أرجع فيب(ن - ١) + فيب(ن - ٢)\n}\nاطبع(فيب(٢٠))");
        ok("دالة أولي؟(ع) {\n إذا ع < ٢ { أرجع خطأ }\n لكل ق في ٢..ع {\n  إذا ق * ق > ع { توقف }\n  إذا ع % ق == ٠ { أرجع خطأ }\n }\n أرجع صحيح\n}\nاطبع(أولي؟(٧))");
        ok("دع س = ٠\nطالما س < ١٠ {\n س = س + ١\n إذا س % ٢ == ٠ { استمر }\n اطبع(\"فردي: ${س}\")\n}");
        ok("دالة أ(ن) { أرجع ب(ن) }\nدالة ب(ن) { أرجع ن }\nاطبع(أ(٣))");
        ok("اطبع(مطلق(-٥)، أكبر(٣، ٩)، أصغر(٣، ٩)، ٧ // -٢، -٧ % ٣، ليس خطأ و صحيح)");
    }

    #[test]
    fn wat_output_is_readable() {
        let wat = ok("دالة مربع(ن) { أرجع ن * ن }\nاطبع(\"الناتج: \", مربع(٤٢))").wat;
        assert!(wat.contains("(export \"run\")"));
        assert!(wat.contains("i64.const 42"));
        assert!(wat.contains(";; دالة مربع"));
        assert!(wat.contains("الناتج: "));
    }

    #[test]
    fn rejects_unsupported_with_clear_codes() {
        assert_eq!(err("اطبع([١، ٢])"), 4001);
        assert_eq!(err("اطبع(١ / ٢)"), 4001);
        assert_eq!(err("دع س = ١٫٥"), 4001);
        assert_eq!(err("إذا ١ { }"), 1010);
        assert_eq!(err("دع س = ١\nس = صحيح"), 4002);
        assert_eq!(err("اطبع(ص)"), 1001);
        assert_eq!(err("ثابت ط = ٣\nط = ٤"), 1002);
        assert_eq!(err("توقف"), 1007);
    }
}
