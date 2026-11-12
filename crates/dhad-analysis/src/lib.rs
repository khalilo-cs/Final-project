//! التحليل الثابت للغة ضاد.
//!
//! يبني جدول الرموز ويحل كل استخدام لاسم إلى تعريفه، ويُصدر تشخيصات قبل التشغيل:
//! - ضاد-1001: اسم غير معرَّف، أو مستخدم قبل تعريفه.
//! - ضاد-1002: إسناد إلى ثابت.
//! - ضاد-1006 / ضاد-1007: «أرجع» خارج دالة، «توقف»/«استمر» خارج حلقة.
//! - ضاد-3001: متغير غير مستخدم (تحذير).
//! - ضاد-3002: معرّفان لا يختلفان إلا بالهمزة أو التاء المربوطة/الهاء أو الألف المقصورة (تحذير).
//!
//! قاعدة الترتيب تطابق المفسر: في المستوى نفسه يجب أن يسبق التعريفُ الاستخدامَ،
//! أما داخل جسم دالة أو كتلة «اختبر» فيُسمح بالإشارة إلى أسماء تُعرَّف لاحقًا
//! في النطاقات المحيطة، لأن الجسم لا يُنفَّذ إلا عند الاستدعاء.

pub mod catalog;

use dhad_diagnostics::{Diagnostic, Span};
use dhad_syntax::*;
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SymbolKind {
    Variable,
    Constant,
    Function,
    Parameter,
    LoopVariable,
    Module,
}

impl SymbolKind {
    pub fn label(self) -> &'static str {
        match self {
            SymbolKind::Variable => "متغير",
            SymbolKind::Constant => "ثابت",
            SymbolKind::Function => "دالة",
            SymbolKind::Parameter => "معامل",
            SymbolKind::LoopVariable => "متغير حلقة",
            SymbolKind::Module => "وحدة",
        }
    }
}

#[derive(Debug, Clone)]
pub struct Symbol {
    pub name: String,
    pub kind: SymbolKind,
    /// موضع الاسم عند التعريف.
    pub span: Span,
    /// الجملة كاملة (للرموز في المحرر).
    pub decl_span: Span,
    pub params: Vec<String>,
    /// تعليق التوثيق (أسطر «##» قبل التعريف مباشرة).
    pub doc: Option<String>,
    /// نوع القيمة إن أمكن استنتاجه من التعريف الحرفي.
    pub value_type: Option<&'static str>,
    pub top_level: bool,
    pub reads: usize,
}

#[derive(Debug, Clone, Copy)]
pub struct Reference {
    pub span: Span,
    pub symbol: usize,
}

#[derive(Debug, Default)]
pub struct Analysis {
    pub diagnostics: Vec<Diagnostic>,
    pub symbols: Vec<Symbol>,
    pub references: Vec<Reference>,
    /// استخدامات أعضاء الوحدات: (موضع العضو، الوحدة، العضو).
    pub member_refs: Vec<(Span, String, String)>,
    pub parsed: bool,
}

impl Analysis {
    /// الرمز المعرَّف أو المستخدَم عند الإزاحة المعطاة.
    pub fn symbol_at(&self, offset: usize) -> Option<(usize, Span)> {
        let hit = |s: Span| s.start <= offset && offset <= s.end;
        self.references
            .iter()
            .find(|r| hit(r.span))
            .map(|r| (r.symbol, r.span))
            .or_else(|| {
                self.symbols
                    .iter()
                    .position(|s| hit(s.span))
                    .map(|i| (i, self.symbols[i].span))
            })
    }

    /// كل مواضع الرمز: تعريفه واستخداماته.
    pub fn occurrences(&self, symbol: usize) -> Vec<Span> {
        let mut v = vec![self.symbols[symbol].span];
        v.extend(
            self.references
                .iter()
                .filter(|r| r.symbol == symbol)
                .map(|r| r.span),
        );
        v
    }
}

/// تحليل نص مطبَّع (انظر [`dhad_syntax::normalize_source`]).
pub fn analyze(src: &str) -> Analysis {
    let program = match parse(src) {
        Ok(p) => p,
        Err(e) => {
            return Analysis {
                diagnostics: vec![e],
                ..Default::default()
            }
        }
    };
    let mut r = Resolver {
        src,
        an: Analysis {
            parsed: true,
            ..Default::default()
        },
        scopes: Vec::new(),
        pending: Vec::new(),
        loop_depth: 0,
        fn_depth: 0,
    };
    let root = r.push_scope(None, false);
    r.block(&program.stmts, root, true);
    r.finish();
    r.an
}

struct Scope {
    parent: Option<usize>,
    /// جسم دالة أو اختبار: يُنفَّذ لاحقًا، فتصح الإشارة إلى ما يُعرَّف بعده في الخارج.
    deferred: bool,
    names: HashMap<String, usize>,
}

struct Pending {
    name: String,
    span: Span,
    scope: usize,
}

struct Resolver<'a> {
    src: &'a str,
    an: Analysis,
    scopes: Vec<Scope>,
    pending: Vec<Pending>,
    loop_depth: usize,
    fn_depth: usize,
}

impl Resolver<'_> {
    fn push_scope(&mut self, parent: Option<usize>, deferred: bool) -> usize {
        self.scopes.push(Scope {
            parent,
            deferred,
            names: HashMap::new(),
        });
        self.scopes.len() - 1
    }

    fn lookup_now(&self, name: &str, mut scope: usize) -> Option<usize> {
        loop {
            if let Some(&i) = self.scopes[scope].names.get(name) {
                return Some(i);
            }
            scope = self.scopes[scope].parent?;
        }
    }

    #[allow(clippy::too_many_arguments)]
    fn define(
        &mut self,
        scope: usize,
        name: &str,
        kind: SymbolKind,
        span: Span,
        decl_span: Span,
        params: Vec<String>,
        value_type: Option<&'static str>,
    ) -> usize {
        let doc = if matches!(
            kind,
            SymbolKind::Function | SymbolKind::Variable | SymbolKind::Constant
        ) {
            doc_comment(self.src, decl_span.start)
        } else {
            None
        };
        let raw = self.src.get(span.start..span.end).unwrap_or("");
        if kind != SymbolKind::Module && raw.chars().any(dhad_syntax::unicode::is_tashkeel) {
            self.an.diagnostics.push(
                Diagnostic::warning(
                    3003,
                    format!("التشكيل في «{raw}» يُتجاهل؛ الاسم هو «{name}»"),
                )
                .with_span(span),
            );
        }
        self.an.symbols.push(Symbol {
            name: name.to_string(),
            kind,
            span,
            decl_span,
            params,
            doc,
            value_type,
            top_level: scope == 0,
            reads: 0,
        });
        let idx = self.an.symbols.len() - 1;
        self.scopes[scope].names.insert(name.to_string(), idx);
        idx
    }

    fn use_name(&mut self, name: &str, span: Span, scope: usize) {
        if let Some(i) = self.lookup_now(name, scope) {
            self.an.symbols[i].reads += 1;
            self.an.references.push(Reference { span, symbol: i });
        } else if catalog::builtin(name).is_none() {
            self.pending.push(Pending {
                name: name.to_string(),
                span,
                scope,
            });
        }
    }

    /// حل الأسماء المؤجلة بعد اكتمال كل التعريفات.
    fn finish(&mut self) {
        for p in std::mem::take(&mut self.pending) {
            let mut scope = Some(p.scope);
            let mut crossed_deferred = false;
            let mut found = None;
            while let Some(s) = scope {
                if let Some(&i) = self.scopes[s].names.get(&p.name) {
                    found = Some(i);
                    break;
                }
                crossed_deferred |= self.scopes[s].deferred;
                scope = self.scopes[s].parent;
            }
            match found {
                Some(i) if crossed_deferred => {
                    self.an.symbols[i].reads += 1;
                    self.an.references.push(Reference {
                        span: p.span,
                        symbol: i,
                    });
                }
                Some(i) => {
                    self.an.references.push(Reference {
                        span: p.span,
                        symbol: i,
                    });
                    self.an.symbols[i].reads += 1;
                    self.an.diagnostics.push(
                        Diagnostic::error(1001, format!("«{}» مستخدم قبل تعريفه", p.name))
                            .with_help("انقل التعريف إلى ما قبل هذا السطر.")
                            .with_span(p.span),
                    );
                }
                None => {
                    let mut d = Diagnostic::error(1001, format!("المتغير «{}» غير معرَّف", p.name));
                    if catalog::module(&p.name).is_some() {
                        d = d.with_help(format!("أضف في أول البرنامج: استورد {}", p.name));
                    } else if let Some(s) = self.suggest(&p.name) {
                        d = d.with_help(format!("هل تقصد «{s}»؟"));
                    }
                    self.an.diagnostics.push(d.with_span(p.span));
                }
            }
        }

        for s in &self.an.symbols {
            let unused_kind = matches!(
                s.kind,
                SymbolKind::Variable | SymbolKind::Constant | SymbolKind::LoopVariable
            );
            if unused_kind && s.reads == 0 && !s.name.starts_with('_') {
                self.an.diagnostics.push(
                    Diagnostic::warning(3001, format!("«{}» معرَّف ولم يُستخدم", s.name))
                        .with_span(s.span),
                );
            }
        }

        let mut seen: HashMap<String, &Symbol> = HashMap::new();
        let mut warned = Vec::new();
        for s in &self.an.symbols {
            let key = confusable_key(&s.name);
            match seen.get(&key) {
                Some(prev) if prev.name != s.name => warned.push(
                    Diagnostic::warning(
                        3002,
                        format!(
                            "«{}» و«{}» لا يختلفان إلا بالهمزة أو التاء المربوطة أو الياء",
                            s.name, prev.name
                        ),
                    )
                    .with_span(s.span),
                ),
                Some(_) => {}
                None => {
                    seen.insert(key, s);
                }
            }
        }
        self.an.diagnostics.extend(warned);
        self.an
            .diagnostics
            .sort_by_key(|d| d.span.map(|s| s.start).unwrap_or(0));
    }

    fn suggest(&self, name: &str) -> Option<String> {
        let mut candidates: Vec<&str> = self.an.symbols.iter().map(|s| s.name.as_str()).collect();
        candidates.extend(catalog::BUILTINS.iter().map(|b| b.name));
        candidates
            .into_iter()
            .map(|c| (levenshtein(name, c), c))
            .filter(|(d, c)| *d > 0 && *d <= 2.max(c.chars().count() / 3))
            .min_by_key(|(d, _)| *d)
            .map(|(_, c)| c.to_string())
    }

    fn block(&mut self, stmts: &[Stmt], scope: usize, _top: bool) {
        for s in stmts {
            self.stmt(s, scope);
        }
    }

    fn child_block(&mut self, b: &Block, parent: usize) {
        let scope = self.push_scope(Some(parent), false);
        self.block(&b.stmts, scope, false);
    }

    fn stmt(&mut self, s: &Stmt, scope: usize) {
        match &s.kind {
            StmtKind::Let {
                name,
                name_span,
                value,
                is_const,
            } => {
                self.expr(value, scope);
                let kind = if *is_const {
                    SymbolKind::Constant
                } else {
                    SymbolKind::Variable
                };
                let params = match &value.kind {
                    ExprKind::Ident(f) => self
                        .lookup_now(f, scope)
                        .map(|i| self.an.symbols[i].params.clone())
                        .unwrap_or_default(),
                    _ => Vec::new(),
                };
                self.define(
                    scope,
                    name,
                    kind,
                    *name_span,
                    s.span,
                    params,
                    literal_type(value),
                );
            }
            StmtKind::Assign { target, value } => {
                self.expr(value, scope);
                match &target.kind {
                    ExprKind::Ident(name) => match self.lookup_now(name, scope) {
                        Some(i) => {
                            self.an.references.push(Reference {
                                span: target.span,
                                symbol: i,
                            });
                            if self.an.symbols[i].kind == SymbolKind::Constant {
                                self.an.diagnostics.push(
                                    Diagnostic::error(
                                        1002,
                                        format!("«{name}» ثابت ولا يمكن تغيير قيمته"),
                                    )
                                    .with_span(target.span),
                                );
                            }
                        }
                        None => self.use_name(name, target.span, scope),
                    },
                    _ => self.expr(target, scope),
                }
            }
            StmtKind::If {
                cond,
                then,
                elifs,
                otherwise,
            } => {
                self.expr(cond, scope);
                self.child_block(then, scope);
                for (c, b) in elifs {
                    self.expr(c, scope);
                    self.child_block(b, scope);
                }
                if let Some(b) = otherwise {
                    self.child_block(b, scope);
                }
            }
            StmtKind::While { cond, body } => {
                self.expr(cond, scope);
                self.loop_depth += 1;
                self.child_block(body, scope);
                self.loop_depth -= 1;
            }
            StmtKind::For {
                var,
                var_span,
                iter,
                body,
            } => {
                self.expr(iter, scope);
                let inner = self.push_scope(Some(scope), false);
                self.define(
                    inner,
                    var,
                    SymbolKind::LoopVariable,
                    *var_span,
                    s.span,
                    vec![],
                    None,
                );
                self.loop_depth += 1;
                self.block(&body.stmts, inner, false);
                self.loop_depth -= 1;
            }
            StmtKind::FnDecl {
                name,
                name_span,
                params,
                body,
            } => {
                let pnames: Vec<String> = params.iter().map(|(p, _)| p.clone()).collect();
                self.define(
                    scope,
                    name,
                    SymbolKind::Function,
                    *name_span,
                    s.span,
                    pnames,
                    None,
                );
                let inner = self.push_scope(Some(scope), true);
                for (p, ps) in params {
                    self.define(inner, p, SymbolKind::Parameter, *ps, *ps, vec![], None);
                }
                let saved_loop = std::mem::replace(&mut self.loop_depth, 0);
                self.fn_depth += 1;
                self.block(&body.stmts, inner, false);
                self.fn_depth -= 1;
                self.loop_depth = saved_loop;
            }
            StmtKind::Return(e) => {
                if let Some(e) = e {
                    self.expr(e, scope);
                }
                if self.fn_depth == 0 {
                    self.an
                        .diagnostics
                        .push(Diagnostic::error(1006, "«أرجع» خارج دالة").with_span(s.span));
                }
            }
            StmtKind::Break | StmtKind::Continue => {
                if self.loop_depth == 0 {
                    let w = if matches!(s.kind, StmtKind::Break) {
                        "توقف"
                    } else {
                        "استمر"
                    };
                    self.an.diagnostics.push(
                        Diagnostic::error(1007, format!("«{w}» خارج حلقة")).with_span(s.span),
                    );
                }
            }
            StmtKind::Import { path } => {
                let name = &path[0];
                if catalog::module(name).is_some() {
                    self.define(
                        scope,
                        name,
                        SymbolKind::Module,
                        s.span,
                        s.span,
                        vec![],
                        None,
                    );
                    // الاستيراد وحده استخدام مقصود؛ لا نحذّر منه كمتغير غير مستخدم.
                } else {
                    self.an.diagnostics.push(
                        Diagnostic::error(1009, format!("الوحدة «{name}» غير موجودة"))
                            .with_span(s.span),
                    );
                }
            }
            StmtKind::Test { body, .. } => {
                let inner = self.push_scope(Some(scope), true);
                let saved_loop = std::mem::replace(&mut self.loop_depth, 0);
                self.block(&body.stmts, inner, false);
                self.loop_depth = saved_loop;
            }
            StmtKind::Expr(e) => self.expr(e, scope),
        }
    }

    fn expr(&mut self, e: &Expr, scope: usize) {
        match &e.kind {
            ExprKind::Ident(name) => self.use_name(name, e.span, scope),
            ExprKind::Str(segs) => {
                for seg in segs {
                    if let StrSeg::Expr(x) = seg {
                        self.expr(x, scope);
                    }
                }
            }
            ExprKind::List(items) => items.iter().for_each(|i| self.expr(i, scope)),
            ExprKind::Dict(pairs) => {
                for (k, v) in pairs {
                    self.expr(k, scope);
                    self.expr(v, scope);
                }
            }
            ExprKind::Binary { left, right, .. } => {
                self.expr(left, scope);
                self.expr(right, scope);
            }
            ExprKind::Unary { expr, .. } => self.expr(expr, scope),
            ExprKind::Call { callee, args } => {
                self.expr(callee, scope);
                args.iter().for_each(|a| self.expr(a, scope));
            }
            ExprKind::Index { obj, index } => {
                self.expr(obj, scope);
                self.expr(index, scope);
            }
            ExprKind::Member { obj, name } => {
                self.expr(obj, scope);
                if let ExprKind::Ident(m) = &obj.kind {
                    if let Some(i) = self.lookup_now(m, scope) {
                        if self.an.symbols[i].kind == SymbolKind::Module {
                            let member_span = Span::new(e.span.end - name.len(), e.span.end);
                            if catalog::module_member(m, name).is_none() {
                                self.an.diagnostics.push(
                                    Diagnostic::error(
                                        2003,
                                        format!("الوحدة «{m}» لا تحتوي «{name}»"),
                                    )
                                    .with_span(member_span),
                                );
                            }
                            self.an
                                .member_refs
                                .push((member_span, m.clone(), name.clone()));
                        }
                    }
                }
            }
            ExprKind::Range { from, to } => {
                self.expr(from, scope);
                self.expr(to, scope);
            }
            ExprKind::Int(_) | ExprKind::Float(_) | ExprKind::Bool(_) | ExprKind::Null => {}
        }
    }
}

fn literal_type(e: &Expr) -> Option<&'static str> {
    Some(match &e.kind {
        ExprKind::Int(_) => "عدد_صحيح",
        ExprKind::Float(_) => "عدد_عشري",
        ExprKind::Str(_) => "نص",
        ExprKind::Bool(_) => "منطقي",
        ExprKind::Null => "عدم",
        ExprKind::List(_) => "قائمة",
        ExprKind::Dict(_) => "قاموس",
        ExprKind::Range { .. } => "مدى",
        ExprKind::Unary { op: UnOp::Not, .. } => "منطقي",
        ExprKind::Binary { op, .. } => match op {
            BinOp::Eq
            | BinOp::NotEq
            | BinOp::Lt
            | BinOp::Gt
            | BinOp::LtEq
            | BinOp::GtEq
            | BinOp::And
            | BinOp::Or
            | BinOp::In => "منطقي",
            BinOp::Div => "عدد_عشري",
            _ => return None,
        },
        _ => return None,
    })
}

/// أسطر «##» المتتالية قبل السطر الذي يبدأ عند `offset`.
fn doc_comment(src: &str, offset: usize) -> Option<String> {
    let line_start = src[..offset.min(src.len())]
        .rfind('\n')
        .map(|i| i + 1)
        .unwrap_or(0);
    let mut lines = Vec::new();
    let mut end = line_start;
    while end > 0 {
        let prev_start = src[..end - 1].rfind('\n').map(|i| i + 1).unwrap_or(0);
        let line = src[prev_start..end - 1].trim();
        match line.strip_prefix("##") {
            Some(text) => lines.push(text.trim().to_string()),
            None => break,
        }
        end = prev_start;
    }
    if lines.is_empty() {
        None
    } else {
        lines.reverse();
        Some(lines.join("\n"))
    }
}

/// مفتاح المقارنة للمعرّفات المتشابهة بصريًا أو إملائيًا.
pub fn confusable_key(name: &str) -> String {
    name.chars()
        .map(|c| match c {
            'أ' | 'إ' | 'آ' | 'ٱ' => 'ا',
            'ة' => 'ه',
            'ى' => 'ي',
            'ؤ' => 'و',
            'ئ' => 'ي',
            other => other,
        })
        .collect()
}

fn levenshtein(a: &str, b: &str) -> usize {
    let a: Vec<char> = a.chars().collect();
    let b: Vec<char> = b.chars().collect();
    let mut prev: Vec<usize> = (0..=b.len()).collect();
    let mut cur = vec![0; b.len() + 1];
    for (i, ca) in a.iter().enumerate() {
        cur[0] = i + 1;
        for (j, cb) in b.iter().enumerate() {
            let cost = usize::from(ca != cb);
            cur[j + 1] = (prev[j + 1] + 1).min(cur[j] + 1).min(prev[j] + cost);
        }
        std::mem::swap(&mut prev, &mut cur);
    }
    prev[b.len()]
}

#[cfg(test)]
mod tests {
    use super::*;

    fn codes(src: &str) -> Vec<u16> {
        analyze(&normalize_source(src))
            .diagnostics
            .iter()
            .map(|d| d.code)
            .collect()
    }

    #[test]
    fn clean_program_has_no_diagnostics() {
        let src = "استورد رياضيات\nدالة م(ن) {\n أرجع رياضيات.جذر(ن)\n}\nاطبع(م(٤))\n";
        assert!(codes(src).is_empty(), "{:?}", codes(src));
    }

    #[test]
    fn undefined_and_suggestion() {
        let a = analyze("دع المجموع = ١\nاطبع(المجموغ)");
        let d = a.diagnostics.iter().find(|d| d.code == 1001).unwrap();
        assert!(d.help.as_deref().unwrap().contains("المجموع"));
    }

    #[test]
    fn use_before_definition_at_top_level() {
        assert_eq!(codes("اطبع(س)\nدع س = ١"), vec![1001]);
    }

    #[test]
    fn functions_may_reference_later_globals() {
        let src = "دالة أ() { أرجع ب() }\nدالة ب() { أرجع ١ }\nاطبع(أ())";
        assert!(codes(src).is_empty(), "{:?}", codes(src));
    }

    #[test]
    fn missing_import_hint() {
        let a = analyze("اطبع(رياضيات.جذر(٤))");
        assert!(a.diagnostics[0]
            .help
            .as_deref()
            .unwrap()
            .contains("استورد رياضيات"));
    }

    #[test]
    fn unknown_module_member() {
        assert_eq!(codes("استورد رياضيات\nاطبع(رياضيات.جيب(١))"), vec![2003]);
        assert!(codes("استورد قوائم\nاطبع(قوائم.رتّب([٢، ١]))").is_empty());
    }

    #[test]
    fn const_assignment_return_break() {
        assert_eq!(codes("ثابت ط = ٣\nط = ٤\nاطبع(ط)"), vec![1002]);
        assert_eq!(codes("أرجع ١"), vec![1006]);
        assert_eq!(codes("توقف"), vec![1007]);
        assert!(codes("طالما صحيح { توقف }").is_empty());
    }

    #[test]
    fn unused_and_confusable_warnings() {
        assert_eq!(codes("دع س = ١"), vec![3001]);
        assert!(codes("دع _س = ١").is_empty());
        let c = codes("دع أسماء = ١\nدع اسماء = ٢\nاطبع(أسماء، اسماء)");
        assert_eq!(c, vec![3002]);
        assert_eq!(codes("دع عَدَد = ٣\nاطبع(عدد)"), vec![3003]);
    }

    #[test]
    fn symbol_lookup_and_docs() {
        let src = "## يجمع عددين\nدالة جمع(أ، ب) {\n أرجع أ + ب\n}\nاطبع(جمع(١، ٢))";
        let a = analyze(src);
        let call = src.rfind("جمع").unwrap();
        let (sym, _) = a.symbol_at(call + 1).unwrap();
        let s = &a.symbols[sym];
        assert_eq!(s.kind, SymbolKind::Function);
        assert_eq!(s.params, vec!["أ", "ب"]);
        assert_eq!(s.doc.as_deref(), Some("يجمع عددين"));
        assert_eq!(a.occurrences(sym).len(), 2);
    }

    #[test]
    fn analysis_is_quiet_on_all_examples() {
        let dir = concat!(env!("CARGO_MANIFEST_DIR"), "/../../examples");
        for entry in std::fs::read_dir(dir).unwrap() {
            let path = entry.unwrap().path();
            if path.extension().is_some_and(|e| e == "ضاد") {
                let src = normalize_source(&std::fs::read_to_string(&path).unwrap());
                let errors: Vec<_> = analyze(&src)
                    .diagnostics
                    .into_iter()
                    .filter(|d| d.severity == dhad_diagnostics::Severity::Error)
                    .collect();
                // المثال الوحيد ذو الخطأ المتعمد خطؤه وقت التشغيل (ضاد-1003) لا ثابت.
                assert!(errors.is_empty(), "{}: {:?}", path.display(), errors);
            }
        }
    }

    #[test]
    fn catalog_matches_interpreter() {
        let it = dhad_interp::Interp::new(Box::new(std::io::sink()));
        for b in catalog::BUILTINS {
            assert!(
                it.globals.get(b.name).is_some(),
                "دالة مدمجة غير موجودة في المفسر: {}",
                b.name
            );
        }
        for (m, _, members) in catalog::MODULES {
            let dhad_interp::Value::Dict(d) = dhad_interp::builtins::module(m).expect(m) else {
                panic!()
            };
            let keys: Vec<String> = d
                .borrow()
                .iter()
                .filter_map(|(k, _)| match k {
                    dhad_interp::Value::Str(s) => Some(s.to_string()),
                    _ => None,
                })
                .filter(|k| k != "__اسم__")
                .collect();
            assert_eq!(keys.len(), members.len(), "عدد أعضاء {m}");
            for i in members.iter() {
                assert!(
                    keys.contains(&dhad_syntax::unicode::strip_tashkeel(i.name)),
                    "{m}.{}",
                    i.name
                );
            }
        }
    }
}
