//! المحلل النحوي (recursive descent + Pratt للتعبيرات).

use crate::ast::*;
use crate::lexer::{tokenize, Kw, StrPart, Tok, Token};
use dhad_diagnostics::{Diagnostic, Span};

/// تحليل برنامج كامل. يجب أن يكون النص مطبَّعًا مسبقًا.
pub fn parse(src: &str) -> Result<Program, Diagnostic> {
    let tokens = tokenize(src)?;
    let mut p = Parser {
        tokens,
        pos: 0,
        base: 0,
    };
    let stmts = p.program()?;
    Ok(Program { stmts })
}

/// تحليل تعبير منفرد (يُستخدم للتعابير المدمجة داخل النصوص وفي REPL).
pub fn parse_expression(src: &str, base_offset: usize) -> Result<Expr, Diagnostic> {
    let tokens = tokenize(src)?;
    let mut p = Parser {
        tokens,
        pos: 0,
        base: base_offset,
    };
    p.skip_newlines();
    let e = p.expression()?;
    p.skip_newlines();
    if !p.at(&Tok::Eof) {
        return Err(p.unexpected("نهاية التعبير"));
    }
    Ok(e)
}

struct Parser {
    tokens: Vec<Token>,
    pos: usize,
    /// إزاحة تُضاف إلى كل المواقع (للتعابير المدمجة داخل النصوص).
    base: usize,
}

impl Parser {
    fn peek(&self) -> &Token {
        &self.tokens[self.pos.min(self.tokens.len() - 1)]
    }

    fn peek_tok(&self) -> &Tok {
        &self.peek().tok
    }

    fn peek_tok_at(&self, n: usize) -> &Tok {
        &self.tokens[(self.pos + n).min(self.tokens.len() - 1)].tok
    }

    fn span(&self) -> Span {
        let s = self.peek().span;
        Span::new(s.start + self.base, s.end + self.base)
    }

    fn prev_span(&self) -> Span {
        let s = self.tokens[self.pos.saturating_sub(1)].span;
        Span::new(s.start + self.base, s.end + self.base)
    }

    fn at(&self, tok: &Tok) -> bool {
        self.peek_tok() == tok
    }

    fn at_kw(&self, kw: Kw) -> bool {
        matches!(self.peek_tok(), Tok::Kw(k) if *k == kw)
    }

    fn advance(&mut self) -> Token {
        let t = self.peek().clone();
        if self.pos < self.tokens.len() - 1 {
            self.pos += 1;
        }
        t
    }

    fn eat(&mut self, tok: &Tok) -> bool {
        if self.at(tok) {
            self.advance();
            true
        } else {
            false
        }
    }

    fn eat_kw(&mut self, kw: Kw) -> bool {
        if self.at_kw(kw) {
            self.advance();
            true
        } else {
            false
        }
    }

    fn skip_newlines(&mut self) {
        while self.at(&Tok::Newline) {
            self.advance();
        }
    }

    fn unexpected(&self, expected: &str) -> Diagnostic {
        Diagnostic::error(
            1,
            format!(
                "رمز غير متوقع: {}، كان المتوقع {expected}",
                self.peek_tok().describe()
            ),
        )
        .with_span(self.span())
    }

    fn expect(&mut self, tok: Tok, expected: &str) -> Result<Token, Diagnostic> {
        if self.at(&tok) {
            Ok(self.advance())
        } else {
            Err(self.unexpected(expected))
        }
    }

    fn expect_ident(&mut self, what: &str) -> Result<(String, Span), Diagnostic> {
        match self.peek_tok().clone() {
            Tok::Ident(name) => {
                let span = self.span();
                self.advance();
                Ok((name, span))
            }
            Tok::Kw(k) => Err(Diagnostic::error(
                5,
                format!(
                    "«{}» كلمة محجوزة في اللغة ولا يمكن استخدامها هنا (المتوقع: {what})",
                    k.display()
                ),
            )
            .with_span(self.span())),
            _ => Err(self.unexpected(what)),
        }
    }

    /// نهاية جملة: سطر جديد أو } أو نهاية الملف.
    fn end_stmt(&mut self) -> Result<(), Diagnostic> {
        if self.at(&Tok::Newline) {
            self.skip_newlines();
            Ok(())
        } else if self.at(&Tok::RBrace) || self.at(&Tok::Eof) {
            Ok(())
        } else {
            Err(self.unexpected("نهاية السطر"))
        }
    }

    fn program(&mut self) -> Result<Vec<Stmt>, Diagnostic> {
        let mut stmts = Vec::new();
        self.skip_newlines();
        while !self.at(&Tok::Eof) {
            stmts.push(self.statement()?);
            self.skip_newlines();
        }
        Ok(stmts)
    }

    fn block(&mut self) -> Result<Block, Diagnostic> {
        let start = self.span();
        self.expect(Tok::LBrace, "«{» لبداية الكتلة")?;
        let mut stmts = Vec::new();
        self.skip_newlines();
        while !self.at(&Tok::RBrace) {
            if self.at(&Tok::Eof) {
                return Err(Diagnostic::error(2, "الكتلة «{» لم تُغلق بـ «}»").with_span(start));
            }
            stmts.push(self.statement()?);
            self.skip_newlines();
        }
        self.expect(Tok::RBrace, "«}»")?;
        Ok(Block {
            stmts,
            span: start.merge(self.prev_span()),
        })
    }

    fn statement(&mut self) -> Result<Stmt, Diagnostic> {
        let start = self.span();
        let kind = match self.peek_tok().clone() {
            Tok::Kw(Kw::Let) | Tok::Kw(Kw::Const) => {
                let is_const = self.at_kw(Kw::Const);
                self.advance();
                let (name, name_span) = self.expect_ident("اسم متغير")?;
                // تلميح نوع اختياري: دع س: عدد = ١
                if self.eat(&Tok::Colon) {
                    self.expect_ident("اسم نوع")?;
                }
                self.expect(Tok::Assign, "«=» بعد اسم المتغير")?;
                let value = self.expression()?;
                self.end_stmt()?;
                StmtKind::Let {
                    name,
                    name_span,
                    value,
                    is_const,
                }
            }
            Tok::Kw(Kw::If) => {
                self.advance();
                let cond = self.expression()?;
                let then = self.block()?;
                let mut elifs = Vec::new();
                let mut otherwise = None;
                loop {
                    // نسمح بسطر جديد قبل «وإلا» بشرط أن تتبعه فعلًا.
                    let save = self.pos;
                    self.skip_newlines();
                    if self.eat_kw(Kw::Else) {
                        if self.eat_kw(Kw::If) {
                            let c = self.expression()?;
                            let b = self.block()?;
                            elifs.push((c, b));
                            continue;
                        }
                        otherwise = Some(self.block()?);
                    } else {
                        self.pos = save;
                    }
                    break;
                }
                self.end_stmt()?;
                StmtKind::If {
                    cond,
                    then,
                    elifs,
                    otherwise,
                }
            }
            Tok::Kw(Kw::While) => {
                self.advance();
                let cond = self.expression()?;
                let body = self.block()?;
                self.end_stmt()?;
                StmtKind::While { cond, body }
            }
            Tok::Kw(Kw::For) => {
                self.advance();
                let (var, var_span) = self.expect_ident("اسم متغير الحلقة")?;
                if !self.eat_kw(Kw::In) {
                    return Err(self.unexpected("«في» بعد اسم المتغير"));
                }
                let iter = self.expression()?;
                let body = self.block()?;
                self.end_stmt()?;
                StmtKind::For {
                    var,
                    var_span,
                    iter,
                    body,
                }
            }
            Tok::Kw(Kw::Fn) => {
                self.advance();
                let (name, _) = self.expect_ident("اسم الدالة")?;
                self.expect(Tok::LParen, "«(» بعد اسم الدالة")?;
                let mut params = Vec::new();
                if !self.at(&Tok::RParen) {
                    loop {
                        params.push(self.expect_ident("اسم معامل")?);
                        if !self.eat(&Tok::Comma) {
                            break;
                        }
                    }
                }
                self.expect(Tok::RParen, "«)» بعد المعاملات")?;
                let body = self.block()?;
                self.end_stmt()?;
                StmtKind::FnDecl { name, params, body }
            }
            Tok::Kw(Kw::Return) => {
                self.advance();
                let value = if self.at(&Tok::Newline) || self.at(&Tok::RBrace) || self.at(&Tok::Eof)
                {
                    None
                } else {
                    Some(self.expression()?)
                };
                self.end_stmt()?;
                StmtKind::Return(value)
            }
            Tok::Kw(Kw::Break) => {
                self.advance();
                self.end_stmt()?;
                StmtKind::Break
            }
            Tok::Kw(Kw::Continue) => {
                self.advance();
                self.end_stmt()?;
                StmtKind::Continue
            }
            Tok::Kw(Kw::Import) => {
                self.advance();
                let mut path = vec![self.expect_ident("اسم وحدة")?.0];
                while self.eat(&Tok::Dot) {
                    path.push(self.expect_ident("اسم وحدة فرعية")?.0);
                }
                self.end_stmt()?;
                StmtKind::Import { path }
            }
            Tok::Kw(Kw::Test) => {
                self.advance();
                let name = match self.peek_tok().clone() {
                    Tok::Str(parts) => {
                        self.advance();
                        parts
                            .iter()
                            .map(|p| match p {
                                StrPart::Text(t) => t.clone(),
                                StrPart::Expr { source, .. } => format!("${{{source}}}"),
                            })
                            .collect::<String>()
                    }
                    _ => return Err(self.unexpected("نص يصف الاختبار")),
                };
                let body = self.block()?;
                self.end_stmt()?;
                StmtKind::Test { name, body }
            }
            Tok::Kw(k @ (Kw::Else | Kw::In)) => {
                return Err(
                    Diagnostic::error(1, format!("الكلمة «{}» لا تبدأ جملة", k.display()))
                        .with_span(start),
                );
            }
            _ => {
                let expr = self.expression()?;
                if self.eat(&Tok::Assign) {
                    match expr.kind {
                        ExprKind::Ident(_) | ExprKind::Index { .. } | ExprKind::Member { .. } => {}
                        _ => {
                            return Err(Diagnostic::error(1012, "لا يمكن الإسناد إلى هذا التعبير")
                                .with_span(expr.span))
                        }
                    }
                    let value = self.expression()?;
                    self.end_stmt()?;
                    StmtKind::Assign {
                        target: expr,
                        value,
                    }
                } else {
                    self.end_stmt()?;
                    StmtKind::Expr(expr)
                }
            }
        };
        Ok(Stmt {
            kind,
            span: start.merge(self.prev_span()),
        })
    }

    // ---------- التعبيرات ----------

    pub(crate) fn expression(&mut self) -> Result<Expr, Diagnostic> {
        self.binary(0)
    }

    fn binop_at(&self) -> Option<(BinOp, u8)> {
        Some(match self.peek_tok() {
            Tok::Kw(Kw::Or) => (BinOp::Or, 1),
            Tok::Kw(Kw::And) => (BinOp::And, 2),
            Tok::EqEq => (BinOp::Eq, 3),
            Tok::NotEq => (BinOp::NotEq, 3),
            Tok::Kw(Kw::In) => (BinOp::In, 3),
            Tok::Lt => (BinOp::Lt, 4),
            Tok::Gt => (BinOp::Gt, 4),
            Tok::LtEq => (BinOp::LtEq, 4),
            Tok::GtEq => (BinOp::GtEq, 4),
            Tok::Plus => (BinOp::Add, 6),
            Tok::Minus => (BinOp::Sub, 6),
            Tok::Star => (BinOp::Mul, 7),
            Tok::Slash => (BinOp::Div, 7),
            Tok::SlashSlash => (BinOp::IntDiv, 7),
            Tok::Percent => (BinOp::Mod, 7),
            _ => return None,
        })
    }

    fn binary(&mut self, min_prec: u8) -> Result<Expr, Diagnostic> {
        let mut left = self.unary()?;
        loop {
            // المدى «..» بأولوية 5: بين المقارنة والجمع.
            if self.at(&Tok::DotDot) && min_prec <= 5 {
                self.advance();
                let right = self.binary(6)?;
                let span = left.span.merge(right.span);
                left = Expr {
                    kind: ExprKind::Range {
                        from: Box::new(left),
                        to: Box::new(right),
                    },
                    span,
                };
                continue;
            }
            let Some((op, prec)) = self.binop_at() else {
                break;
            };
            if prec < min_prec {
                break;
            }
            self.advance();
            let right = self.binary(prec + 1)?;
            let span = left.span.merge(right.span);
            left = Expr {
                kind: ExprKind::Binary {
                    op,
                    left: Box::new(left),
                    right: Box::new(right),
                },
                span,
            };
        }
        Ok(left)
    }

    fn unary(&mut self) -> Result<Expr, Diagnostic> {
        let start = self.span();
        if self.eat_kw(Kw::Not) {
            let e = self.unary()?;
            let span = start.merge(e.span);
            return Ok(Expr {
                kind: ExprKind::Unary {
                    op: UnOp::Not,
                    expr: Box::new(e),
                },
                span,
            });
        }
        if self.eat(&Tok::Minus) {
            let e = self.unary()?;
            let span = start.merge(e.span);
            return Ok(Expr {
                kind: ExprKind::Unary {
                    op: UnOp::Neg,
                    expr: Box::new(e),
                },
                span,
            });
        }
        self.postfix()
    }

    fn postfix(&mut self) -> Result<Expr, Diagnostic> {
        let mut e = self.primary()?;
        loop {
            if self.at(&Tok::LParen) {
                self.advance();
                let mut args = Vec::new();
                if !self.at(&Tok::RParen) {
                    loop {
                        args.push(self.expression()?);
                        if !self.eat(&Tok::Comma) {
                            break;
                        }
                        if self.at(&Tok::RParen) {
                            break;
                        }
                    }
                }
                self.expect(Tok::RParen, "«)» لإغلاق الاستدعاء")?;
                let span = e.span.merge(self.prev_span());
                e = Expr {
                    kind: ExprKind::Call {
                        callee: Box::new(e),
                        args,
                    },
                    span,
                };
            } else if self.at(&Tok::LBracket) {
                self.advance();
                let index = self.expression()?;
                self.expect(Tok::RBracket, "«]»")?;
                let span = e.span.merge(self.prev_span());
                e = Expr {
                    kind: ExprKind::Index {
                        obj: Box::new(e),
                        index: Box::new(index),
                    },
                    span,
                };
            } else if self.at(&Tok::Dot) && !matches!(self.peek_tok_at(1), Tok::Dot) {
                self.advance();
                let (name, nspan) = self.expect_ident("اسم عضو بعد «.»")?;
                let span = e.span.merge(nspan);
                e = Expr {
                    kind: ExprKind::Member {
                        obj: Box::new(e),
                        name,
                    },
                    span,
                };
            } else {
                break;
            }
        }
        Ok(e)
    }

    fn primary(&mut self) -> Result<Expr, Diagnostic> {
        let span = self.span();
        let tok = self.peek_tok().clone();
        let kind = match tok {
            Tok::Int(n) => {
                self.advance();
                ExprKind::Int(n)
            }
            Tok::Float(f) => {
                self.advance();
                ExprKind::Float(f)
            }
            Tok::Kw(Kw::True) => {
                self.advance();
                ExprKind::Bool(true)
            }
            Tok::Kw(Kw::False) => {
                self.advance();
                ExprKind::Bool(false)
            }
            Tok::Kw(Kw::Null) => {
                self.advance();
                ExprKind::Null
            }
            Tok::Ident(name) => {
                self.advance();
                ExprKind::Ident(name)
            }
            Tok::Str(parts) => {
                self.advance();
                let mut segs = Vec::new();
                for p in parts {
                    match p {
                        StrPart::Text(t) => segs.push(StrSeg::Text(t)),
                        StrPart::Expr { source, offset } => {
                            let e = parse_expression(&source, self.base + offset)?;
                            segs.push(StrSeg::Expr(e));
                        }
                    }
                }
                ExprKind::Str(segs)
            }
            Tok::LParen => {
                self.advance();
                let e = self.expression()?;
                self.expect(Tok::RParen, "«)»")?;
                return Ok(Expr {
                    kind: e.kind,
                    span: span.merge(self.prev_span()),
                });
            }
            Tok::LBracket => {
                self.advance();
                let mut items = Vec::new();
                if !self.at(&Tok::RBracket) {
                    loop {
                        items.push(self.expression()?);
                        if !self.eat(&Tok::Comma) {
                            break;
                        }
                        if self.at(&Tok::RBracket) {
                            break;
                        }
                    }
                }
                self.expect(Tok::RBracket, "«]» لإغلاق القائمة")?;
                ExprKind::List(items)
            }
            Tok::LBrace => {
                self.advance();
                let mut pairs = Vec::new();
                self.skip_newlines();
                if !self.at(&Tok::RBrace) {
                    loop {
                        self.skip_newlines();
                        let k = self.expression()?;
                        self.expect(Tok::Colon, "«:» بين المفتاح والقيمة")?;
                        let v = self.expression()?;
                        pairs.push((k, v));
                        self.skip_newlines();
                        if !self.eat(&Tok::Comma) {
                            break;
                        }
                        self.skip_newlines();
                        if self.at(&Tok::RBrace) {
                            break;
                        }
                    }
                }
                self.skip_newlines();
                self.expect(Tok::RBrace, "«}» لإغلاق القاموس")?;
                ExprKind::Dict(pairs)
            }
            Tok::Kw(k) => {
                return Err(Diagnostic::error(
                    5,
                    format!("الكلمة المفتاحية «{}» ليست قيمة", k.display()),
                )
                .with_span(span));
            }
            _ => return Err(self.unexpected("قيمة أو تعبير")),
        };
        Ok(Expr {
            kind,
            span: span.merge(self.prev_span()),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_function_and_call() {
        let p = parse("دالة جمع(أ، ب) {\n أرجع أ + ب\n}\nاطبع(جمع(١، ٢))\n").unwrap();
        assert_eq!(p.stmts.len(), 2);
        assert!(matches!(p.stmts[0].kind, StmtKind::FnDecl { ref name, .. } if name == "جمع"));
    }

    #[test]
    fn precedence_mul_over_add_and_range_lowest_arith() {
        let e = parse_expression("١ + ٢ * ٣", 0).unwrap();
        match e.kind {
            ExprKind::Binary {
                op: BinOp::Add,
                right,
                ..
            } => {
                assert!(matches!(
                    right.kind,
                    ExprKind::Binary { op: BinOp::Mul, .. }
                ))
            }
            _ => panic!(),
        }
        let r = parse_expression("٢..ن + ١", 0).unwrap();
        match r.kind {
            ExprKind::Range { to, .. } => {
                assert!(matches!(to.kind, ExprKind::Binary { op: BinOp::Add, .. }))
            }
            _ => panic!("expected range"),
        }
    }

    #[test]
    fn if_elif_else_chain() {
        let src = "إذا س > ١ { اطبع(١) } وإلا إذا س > ٠ { اطبع(٢) } وإلا { اطبع(٣) }";
        let p = parse(src).unwrap();
        match &p.stmts[0].kind {
            StmtKind::If {
                elifs, otherwise, ..
            } => {
                assert_eq!(elifs.len(), 1);
                assert!(otherwise.is_some());
            }
            _ => panic!(),
        }
    }

    #[test]
    fn keyword_as_name_is_code_5() {
        assert_eq!(parse("دع إذا = ١").unwrap_err().code, 5);
    }

    #[test]
    fn interpolation_is_parsed_into_expressions() {
        let e = parse_expression("\"العمر: ${س + ١}\"", 0).unwrap();
        match e.kind {
            ExprKind::Str(segs) => assert!(matches!(segs[1], StrSeg::Expr(_))),
            _ => panic!(),
        }
    }

    #[test]
    fn dict_literal() {
        let e = parse_expression("{\"أ\": ١، \"ب\": ٢}", 0).unwrap();
        assert!(matches!(e.kind, ExprKind::Dict(ref p) if p.len() == 2));
    }
}
