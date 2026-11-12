//! المحلل اللغوي (Lexer) للغة ضاد.
//!
//! يفترض أن النص مطبَّع مسبقًا بـ [`crate::unicode::normalize_source`].

use crate::unicode::*;
use dhad_diagnostics::{Diagnostic, Span};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kw {
    Let,
    Const,
    If,
    Else,
    While,
    For,
    In,
    Fn,
    Return,
    Break,
    Continue,
    True,
    False,
    And,
    Or,
    Not,
    Null,
    Import,
    Test,
}

impl Kw {
    pub fn from_ident(s: &str) -> Option<Kw> {
        Some(match s {
            "دع" => Kw::Let,
            "ثابت" => Kw::Const,
            "إذا" | "اذا" => Kw::If,
            "وإلا" | "والا" => Kw::Else,
            "طالما" => Kw::While,
            "لكل" => Kw::For,
            "في" => Kw::In,
            "دالة" | "دالّة" => Kw::Fn,
            "أرجع" | "ارجع" => Kw::Return,
            "توقف" => Kw::Break,
            "استمر" => Kw::Continue,
            "صحيح" => Kw::True,
            "خطأ" | "خطا" => Kw::False,
            "و" => Kw::And,
            "أو" | "او" => Kw::Or,
            "ليس" => Kw::Not,
            "عدم" => Kw::Null,
            "استورد" => Kw::Import,
            "اختبر" => Kw::Test,
            _ => return None,
        })
    }

    pub fn display(self) -> &'static str {
        match self {
            Kw::Let => "دع",
            Kw::Const => "ثابت",
            Kw::If => "إذا",
            Kw::Else => "وإلا",
            Kw::While => "طالما",
            Kw::For => "لكل",
            Kw::In => "في",
            Kw::Fn => "دالة",
            Kw::Return => "أرجع",
            Kw::Break => "توقف",
            Kw::Continue => "استمر",
            Kw::True => "صحيح",
            Kw::False => "خطأ",
            Kw::And => "و",
            Kw::Or => "أو",
            Kw::Not => "ليس",
            Kw::Null => "عدم",
            Kw::Import => "استورد",
            Kw::Test => "اختبر",
        }
    }
}

/// جزء من نص حرفي: نص عادي أو مصدر تعبير مدمج مع إزاحته في الملف.
#[derive(Debug, Clone, PartialEq)]
pub enum StrPart {
    Text(String),
    Expr { source: String, offset: usize },
}

#[derive(Debug, Clone, PartialEq)]
pub enum Tok {
    Int(i64),
    Float(f64),
    Str(Vec<StrPart>),
    Ident(String),
    Kw(Kw),
    LParen,
    RParen,
    LBracket,
    RBracket,
    LBrace,
    RBrace,
    Comma,
    Colon,
    Dot,
    DotDot,
    Plus,
    Minus,
    Star,
    Slash,
    SlashSlash,
    Percent,
    Assign,
    EqEq,
    NotEq,
    Lt,
    Gt,
    LtEq,
    GtEq,
    Newline,
    Eof,
}

impl Tok {
    pub fn describe(&self) -> String {
        match self {
            Tok::Int(n) => format!("العدد {n}"),
            Tok::Float(n) => format!("العدد {n}"),
            Tok::Str(_) => "نص".into(),
            Tok::Ident(s) => format!("المعرّف «{s}»"),
            Tok::Kw(k) => format!("الكلمة المفتاحية «{}»", k.display()),
            Tok::LParen => "«(»".into(),
            Tok::RParen => "«)»".into(),
            Tok::LBracket => "«[»".into(),
            Tok::RBracket => "«]»".into(),
            Tok::LBrace => "«{»".into(),
            Tok::RBrace => "«}»".into(),
            Tok::Comma => "فاصلة".into(),
            Tok::Colon => "«:»".into(),
            Tok::Dot => "«.»".into(),
            Tok::DotDot => "«..»".into(),
            Tok::Plus => "«+»".into(),
            Tok::Minus => "«-»".into(),
            Tok::Star => "«*»".into(),
            Tok::Slash => "«/»".into(),
            Tok::SlashSlash => "«//»".into(),
            Tok::Percent => "«%»".into(),
            Tok::Assign => "«=»".into(),
            Tok::EqEq => "«==»".into(),
            Tok::NotEq => "«!=»".into(),
            Tok::Lt => "«<»".into(),
            Tok::Gt => "«>»".into(),
            Tok::LtEq => "«<=»".into(),
            Tok::GtEq => "«>=»".into(),
            Tok::Newline => "نهاية السطر".into(),
            Tok::Eof => "نهاية الملف".into(),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Token {
    pub tok: Tok,
    pub span: Span,
}

struct Lexer<'a> {
    src: &'a str,
    chars: Vec<(usize, char)>,
    pos: usize,
    /// عمق الأقواس ( ) و [ ]: داخلها تُتجاهل نهايات الأسطر.
    depth: usize,
    tokens: Vec<Token>,
    /// مواضع الأقواس المفتوحة للإبلاغ عن قوس غير مغلق.
    open_stack: Vec<(char, usize)>,
}

pub fn tokenize(src: &str) -> Result<Vec<Token>, Diagnostic> {
    let mut lx = Lexer {
        src,
        chars: src.char_indices().collect(),
        pos: 0,
        depth: 0,
        tokens: Vec::new(),
        open_stack: Vec::new(),
    };
    lx.run()?;
    Ok(lx.tokens)
}

impl<'a> Lexer<'a> {
    fn peek(&self) -> Option<char> {
        self.chars.get(self.pos).map(|(_, c)| *c)
    }

    fn peek_at(&self, n: usize) -> Option<char> {
        self.chars.get(self.pos + n).map(|(_, c)| *c)
    }

    fn offset(&self) -> usize {
        self.chars
            .get(self.pos)
            .map(|(i, _)| *i)
            .unwrap_or(self.src.len())
    }

    fn bump(&mut self) -> Option<char> {
        let c = self.peek();
        if c.is_some() {
            self.pos += 1;
        }
        c
    }

    fn push(&mut self, tok: Tok, start: usize) {
        let end = self.offset();
        self.tokens.push(Token {
            tok,
            span: Span::new(start, end),
        });
    }

    fn push_newline(&mut self, start: usize) {
        if self.depth > 0 {
            return;
        }
        if matches!(
            self.tokens.last(),
            Some(Token {
                tok: Tok::Newline,
                ..
            }) | None
        ) {
            return;
        }
        self.tokens.push(Token {
            tok: Tok::Newline,
            span: Span::new(start, start + 1),
        });
    }

    fn run(&mut self) -> Result<(), Diagnostic> {
        while let Some(c) = self.peek() {
            let start = self.offset();
            match c {
                '\n' => {
                    self.bump();
                    self.push_newline(start);
                }
                ' ' | '\t' | '\r' | '\u{FEFF}' | '\u{200F}' | '\u{200E}' => {
                    self.bump();
                }
                '#' => {
                    while let Some(c) = self.peek() {
                        if c == '\n' {
                            break;
                        }
                        self.bump();
                    }
                }
                ';' | '\u{061B}' => {
                    // الفاصلة المنقوطة (اللاتينية أو العربية) فاصل جمل اختياري.
                    self.bump();
                    self.push_newline(start);
                }
                '"' | '\u{00AB}' => {
                    let close = if c == '"' { '"' } else { '\u{00BB}' };
                    self.bump();
                    let parts = self.string(start, close)?;
                    self.push(Tok::Str(parts), start);
                }
                '(' | '[' => {
                    self.bump();
                    self.depth += 1;
                    self.open_stack.push((c, start));
                    self.push(if c == '(' { Tok::LParen } else { Tok::LBracket }, start);
                }
                ')' | ']' => {
                    self.bump();
                    self.depth = self.depth.saturating_sub(1);
                    self.open_stack.pop();
                    self.push(if c == ')' { Tok::RParen } else { Tok::RBracket }, start);
                }
                '{' => {
                    self.bump();
                    self.open_stack.push(('{', start));
                    self.push(Tok::LBrace, start);
                }
                '}' => {
                    self.bump();
                    self.open_stack.pop();
                    self.push(Tok::RBrace, start);
                }
                ':' => {
                    self.bump();
                    self.push(Tok::Colon, start);
                }
                '+' => {
                    self.bump();
                    self.push(Tok::Plus, start);
                }
                '-' | '\u{2212}' => {
                    self.bump();
                    self.push(Tok::Minus, start);
                }
                '*' | '\u{00D7}' => {
                    self.bump();
                    self.push(Tok::Star, start);
                }
                '/' | '\u{00F7}' => {
                    self.bump();
                    if c == '/' && self.peek() == Some('/') {
                        self.bump();
                        self.push(Tok::SlashSlash, start);
                    } else {
                        self.push(Tok::Slash, start);
                    }
                }
                '%' | '\u{066A}' => {
                    self.bump();
                    self.push(Tok::Percent, start);
                }
                '=' => {
                    self.bump();
                    if self.peek() == Some('=') {
                        self.bump();
                        self.push(Tok::EqEq, start);
                    } else {
                        self.push(Tok::Assign, start);
                    }
                }
                '!' => {
                    self.bump();
                    if self.peek() == Some('=') {
                        self.bump();
                        self.push(Tok::NotEq, start);
                    } else {
                        return Err(Diagnostic::error(1, "رمز غير متوقع: «!»")
                            .with_help("للنفي استخدم «ليس»، وللمقارنة «!=».")
                            .with_span(Span::new(start, self.offset())));
                    }
                }
                '\u{2260}' => {
                    self.bump();
                    self.push(Tok::NotEq, start);
                }
                '<' => {
                    self.bump();
                    if self.peek() == Some('=') {
                        self.bump();
                        self.push(Tok::LtEq, start);
                    } else {
                        self.push(Tok::Lt, start);
                    }
                }
                '>' => {
                    self.bump();
                    if self.peek() == Some('=') {
                        self.bump();
                        self.push(Tok::GtEq, start);
                    } else {
                        self.push(Tok::Gt, start);
                    }
                }
                '\u{2264}' => {
                    self.bump();
                    self.push(Tok::LtEq, start);
                }
                '\u{2265}' => {
                    self.bump();
                    self.push(Tok::GtEq, start);
                }
                '.' => {
                    self.bump();
                    if self.peek() == Some('.') {
                        self.bump();
                        self.push(Tok::DotDot, start);
                    } else {
                        self.push(Tok::Dot, start);
                    }
                }
                c if is_comma(c) => {
                    self.bump();
                    self.push(Tok::Comma, start);
                }
                c if is_digit(c) => self.number(start)?,
                c if is_ident_start(c) => self.ident(start)?,
                other => {
                    self.bump();
                    return Err(Diagnostic::error(
                        1,
                        format!("رمز غير متوقع: «{other}» (U+{:04X})", other as u32),
                    )
                    .with_span(Span::new(start, self.offset())));
                }
            }
        }
        if let Some((c, at)) = self.open_stack.last() {
            return Err(Diagnostic::error(2, format!("القوس «{c}» لم يُغلق"))
                .with_span(Span::new(*at, *at + c.len_utf8())));
        }
        let end = self.src.len();
        self.push_newline(end);
        self.tokens.push(Token {
            tok: Tok::Eof,
            span: Span::new(end, end),
        });
        Ok(())
    }

    fn number(&mut self, start: usize) -> Result<(), Diagnostic> {
        let mut text = String::new();
        let mut is_float = false;
        while let Some(c) = self.peek() {
            if let Some(d) = digit_value(c) {
                text.push(char::from_digit(d, 10).unwrap());
                self.bump();
            } else if c == '_' {
                self.bump();
            } else if is_decimal_point(c)
                && !is_float
                && self.peek_at(1).is_some_and(is_digit)
                && !(c == '.' && self.peek_at(1) == Some('.'))
            {
                is_float = true;
                text.push('.');
                self.bump();
            } else {
                break;
            }
        }
        if let Some(c) = self.peek() {
            if is_ident_start(c) {
                self.bump();
                return Err(Diagnostic::error(6, format!("عدد غير صالح: «{text}{c}»"))
                    .with_span(Span::new(start, self.offset())));
            }
        }
        let tok = if is_float {
            Tok::Float(text.parse::<f64>().map_err(|_| {
                Diagnostic::error(6, format!("عدد غير صالح: «{text}»"))
                    .with_span(Span::new(start, self.offset()))
            })?)
        } else {
            match text.parse::<i64>() {
                Ok(n) => Tok::Int(n),
                Err(_) => Tok::Float(text.parse::<f64>().map_err(|_| {
                    Diagnostic::error(6, format!("عدد غير صالح: «{text}»"))
                        .with_span(Span::new(start, self.offset()))
                })?),
            }
        };
        self.push(tok, start);
        Ok(())
    }

    fn ident(&mut self, start: usize) -> Result<(), Diagnostic> {
        let mut raw = String::new();
        while let Some(c) = self.peek() {
            if is_ident_continue(c) {
                raw.push(c);
                self.bump();
            } else {
                break;
            }
        }
        // علامة الاستفهام في نهاية المعرّف اصطلاح للدوال المنطقية: أولي؟
        if matches!(self.peek(), Some('؟') | Some('?')) {
            raw.push('؟');
            self.bump();
        }
        let name = strip_tashkeel(&raw);
        if mixes_scripts(&name) {
            return Err(
                Diagnostic::error(4, format!("المعرّف «{name}» يخلط أحرفًا عربية ولاتينية"))
                    .with_span(Span::new(start, self.offset())),
            );
        }
        let tok = match Kw::from_ident(&name) {
            Some(k) => Tok::Kw(k),
            None => Tok::Ident(name),
        };
        self.push(tok, start);
        Ok(())
    }

    fn string(&mut self, start: usize, close: char) -> Result<Vec<StrPart>, Diagnostic> {
        let mut parts = Vec::new();
        let mut buf = String::new();
        loop {
            let Some(c) = self.bump() else {
                return Err(
                    Diagnostic::error(3, "نص غير مغلق").with_span(Span::new(start, self.src.len()))
                );
            };
            if c == close {
                break;
            }
            match c {
                '\n' => {
                    return Err(Diagnostic::error(3, "نص غير مغلق قبل نهاية السطر")
                        .with_span(Span::new(start, self.offset())));
                }
                '\\' => {
                    let e = self.bump().ok_or_else(|| {
                        Diagnostic::error(3, "نص غير مغلق")
                            .with_span(Span::new(start, self.src.len()))
                    })?;
                    buf.push(match e {
                        'n' | 'س' => '\n',
                        't' | 'ت' => '\t',
                        '0' => '\0',
                        other => other,
                    });
                }
                '$' if self.peek() == Some('{') => {
                    self.bump();
                    if !buf.is_empty() {
                        parts.push(StrPart::Text(std::mem::take(&mut buf)));
                    }
                    let expr_start = self.offset();
                    let mut depth = 1usize;
                    let mut source = String::new();
                    loop {
                        let Some(ch) = self.bump() else {
                            return Err(Diagnostic::error(2, "القوس «{» داخل النص لم يُغلق")
                                .with_span(Span::new(expr_start - 2, self.src.len())));
                        };
                        match ch {
                            '{' => depth += 1,
                            '}' => {
                                depth -= 1;
                                if depth == 0 {
                                    break;
                                }
                            }
                            _ => {}
                        }
                        source.push(ch);
                    }
                    parts.push(StrPart::Expr {
                        source,
                        offset: expr_start,
                    });
                }
                other => buf.push(other),
            }
        }
        if !buf.is_empty() || parts.is_empty() {
            parts.push(StrPart::Text(buf));
        }
        Ok(parts)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn toks(src: &str) -> Vec<Tok> {
        tokenize(src).unwrap().into_iter().map(|t| t.tok).collect()
    }

    #[test]
    fn keywords_and_idents() {
        assert_eq!(
            toks("دع العمر = ٢٥"),
            vec![
                Tok::Kw(Kw::Let),
                Tok::Ident("العمر".into()),
                Tok::Assign,
                Tok::Int(25),
                Tok::Newline,
                Tok::Eof
            ]
        );
    }

    #[test]
    fn numbers_in_both_scripts_and_ranges() {
        assert_eq!(toks("١..٥")[..3], [Tok::Int(1), Tok::DotDot, Tok::Int(5)]);
        assert_eq!(toks("٢٫٧٥")[0], Tok::Float(2.75));
        assert_eq!(toks("2.5")[0], Tok::Float(2.5));
    }

    #[test]
    fn tashkeel_is_ignored_in_identifiers() {
        assert_eq!(toks("عَدَد")[0], Tok::Ident("عدد".into()));
    }

    #[test]
    fn mixed_script_identifier_is_rejected() {
        let err = tokenize("دع عددx = ١").unwrap_err();
        assert_eq!(err.code, 4);
    }

    #[test]
    fn string_interpolation_parts() {
        let t = toks("\"مرحبًا ${اسم}!\"");
        match &t[0] {
            Tok::Str(parts) => {
                assert_eq!(parts.len(), 3);
                assert!(matches!(&parts[1], StrPart::Expr { source, .. } if source == "اسم"));
            }
            other => panic!("unexpected {other:?}"),
        }
    }

    #[test]
    fn newlines_suppressed_inside_parens() {
        let t = toks("اطبع(\n١،\n٢)");
        assert!(!t[..t.len() - 2].contains(&Tok::Newline));
    }

    #[test]
    fn unclosed_paren_reports_code_2() {
        assert_eq!(tokenize("اطبع(١").unwrap_err().code, 2);
    }

    #[test]
    fn unclosed_string_reports_code_3() {
        assert_eq!(tokenize("\"abc").unwrap_err().code, 3);
    }
}
