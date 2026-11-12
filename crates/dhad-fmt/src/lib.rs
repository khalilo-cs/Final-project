//! منسّق لغة ضاد.
//!
//! المبدأ: المنسّق **لا يغيّر الرموز أبدًا**. كل رمز يُنسخ حرفيًا من المصدر — عدا توحيد الفاصلة — (فتبقى الأرقام
//! الشرقية شرقية والتشكيل كما هو)، ولا يتغير إلا ما بين الرموز: المسافات والإزاحة والأسطر
//! الفارغة. بعد التنسيق يُعاد التحليل اللغوي ويُقارَن تسلسل الرموز بالأصل؛ أي اختلاف
//! يُلغي التنسيق ويُعاد خطأ، فلا يمكن أن يغيّر المنسّق معنى برنامج.
//!
//! الأسلوب:
//! - إزاحة ٤ مسافات لكل مستوى «{»، ومستوى إضافي لأسطر استمرار داخل ( ) أو [ ].
//! - مسافة واحدة حول العمليات الثنائية و«=»، ولا مسافة بعد السالب الأحادي.
//! - الفاصلة عربية دائمًا «،»، بلا مسافة قبلها ومسافة واحدة بعدها (وكذلك «:»)؛ لا مسافات داخل ( ) و[ ].
//! - الاستدعاء والفهرسة والعضو والمدى بلا مسافات: `ف(س)`، `ق[٠]`، `و.ع`، `١..١٠`.
//! - التعليق يُسبق بمسافة واحدة، وتُطوى الأسطر الفارغة المتتالية في سطر واحد.

use dhad_diagnostics::{Diagnostic, Span};
use dhad_syntax::{tokenize, Kw, StrPart, Tok, Token};

const INDENT: &str = "    ";

/// تنسيق نص مطبَّع. يعيد خطأً نحويًا إن تعذّر تحليل البرنامج لغويًا.
pub fn format(src: &str) -> Result<String, Diagnostic> {
    let tokens = tokenize(src)?;
    let out = render(src, &tokens);
    let again = tokenize(&out).map_err(|_| internal())?;
    if kinds(&tokens) != kinds(&again) {
        return Err(internal());
    }
    Ok(out)
}

fn internal() -> Diagnostic {
    Diagnostic::error(1, "تعذّر التنسيق دون تغيير معنى البرنامج (خلل في المنسّق)")
        .with_help("الملف لم يُعدَّل. أبلغ عن المشكلة مع البرنامج.")
}

/// تسلسل الرموز دون المواضع ونهايات الأسطر (التي يحق للمنسّق تغييرها).
/// التعابير المدمجة في النصوص تحمل موضعها في الملف، فيُصفَّر لأنه يتغير مع الإزاحة.
fn kinds(tokens: &[Token]) -> Vec<Tok> {
    tokens
        .iter()
        .filter(|t| t.tok != Tok::Newline)
        .map(|t| match &t.tok {
            Tok::Str(parts) => Tok::Str(
                parts
                    .iter()
                    .map(|p| match p {
                        StrPart::Expr { source, .. } => StrPart::Expr {
                            source: source.clone(),
                            offset: 0,
                        },
                        other => other.clone(),
                    })
                    .collect(),
            ),
            other => other.clone(),
        })
        .collect()
}

fn line_starts(src: &str) -> Vec<usize> {
    let mut v = vec![0];
    v.extend(src.match_indices('\n').map(|(i, _)| i + 1));
    v
}

/// موضع بداية التعليق في السطر (علامة # خارج النصوص)، إن وُجد.
fn comment_start(line: &str) -> Option<usize> {
    let mut in_str: Option<char> = None;
    let mut escaped = false;
    for (i, c) in line.char_indices() {
        match in_str {
            Some(close) => {
                if escaped {
                    escaped = false;
                } else if c == '\\' {
                    escaped = true;
                } else if c == close {
                    in_str = None;
                }
            }
            None => match c {
                '"' => in_str = Some('"'),
                '«' => in_str = Some('»'),
                '#' => return Some(i),
                _ => {}
            },
        }
    }
    None
}

fn is_binary_kw(t: &Tok) -> bool {
    matches!(t, Tok::Kw(Kw::And | Kw::Or | Kw::In))
}

fn is_operator(t: &Tok) -> bool {
    matches!(
        t,
        Tok::Plus
            | Tok::Minus
            | Tok::Star
            | Tok::Slash
            | Tok::SlashSlash
            | Tok::Percent
            | Tok::Assign
            | Tok::EqEq
            | Tok::NotEq
            | Tok::Lt
            | Tok::Gt
            | Tok::LtEq
            | Tok::GtEq
    ) || is_binary_kw(t)
}

/// هل السالب في هذا الموضع أحادي؟ (بعد عملية أو فتح قوس أو فاصلة أو كلمة مفتاحية أو في البداية)
fn unary_context(prev: Option<&Tok>) -> bool {
    match prev {
        None => true,
        Some(t) => {
            is_operator(t)
                || matches!(
                    t,
                    Tok::LParen
                        | Tok::LBracket
                        | Tok::LBrace
                        | Tok::Comma
                        | Tok::Colon
                        | Tok::Newline
                        | Tok::DotDot
                )
                || matches!(t, Tok::Kw(k) if !matches!(k, Kw::True | Kw::False | Kw::Null))
        }
    }
}

fn is_value_end(t: &Tok) -> bool {
    matches!(
        t,
        Tok::Ident(_) | Tok::RParen | Tok::RBracket | Tok::Str(_) | Tok::Int(_) | Tok::Float(_)
    ) || matches!(t, Tok::Kw(Kw::True | Kw::False | Kw::Null))
}

/// هل «{» في هذا الموضع بداية قاموس (لا كتلة)؟ القاموس قيمة، فيأتي حيث يُنتظر تعبير.
fn opens_dict(prev: Option<&Tok>) -> bool {
    match prev {
        None => false,
        Some(t) => {
            (is_operator(t) && !matches!(t, Tok::Kw(_)))
                || matches!(t, Tok::LParen | Tok::LBracket | Tok::Comma | Tok::Colon)
                || matches!(t, Tok::Kw(Kw::In | Kw::Return | Kw::And | Kw::Or | Kw::Not))
        }
    }
}

/// هل تُوضع مسافة بين الرمزين المتتاليين في السطر نفسه؟
/// `a_dict`: الرمز الأول «{» قاموس؛ `b_dict`: الرمز الثاني «}» يغلق قاموسًا.
fn space_between(a: &Tok, a_unary: bool, a_dict: bool, b: &Tok, b_dict: bool) -> bool {
    use Tok::*;
    if a_unary || a_dict || b_dict {
        return false;
    }
    match (a, b) {
        (_, Comma) | (_, Colon) | (_, RParen) | (_, RBracket) => false,
        (LParen | LBracket, _) => false,
        (Dot | DotDot, _) | (_, Dot | DotDot) => false,
        (LBrace, RBrace) => false,
        (a, LParen) if is_value_end(a) && !matches!(a, Int(_) | Float(_) | Str(_)) => false,
        (a, LBracket) if is_value_end(a) => false,
        (Newline, _) => true,
        (_, Newline) => false,
        _ => true,
    }
}

fn render(src: &str, tokens: &[Token]) -> String {
    let starts = line_starts(src);
    let line_of = |offset: usize| starts.partition_point(|&s| s <= offset) - 1;
    let n_lines = starts.len();
    let mut by_line: Vec<Vec<&Token>> = vec![Vec::new(); n_lines];
    for t in tokens {
        if t.tok == Tok::Eof {
            continue;
        }
        // نهايات الأسطر الحقيقية نعيد بناءها بأنفسنا؛ نُبقي فقط «؛» و«;» الصريحتين.
        if t.tok == Tok::Newline
            && src
                .get(t.span.start..t.span.end)
                .is_none_or(|s| s.contains('\n'))
        {
            continue;
        }
        by_line[line_of(t.span.start)].push(t);
    }

    let mut out: Vec<String> = Vec::new();
    let (mut brace, mut paren) = (0usize, 0usize);
    let mut prev_global: Option<Tok> = None;
    let mut braces: Vec<bool> = Vec::new();

    for (ln, toks) in by_line.iter().enumerate() {
        let line_end = starts.get(ln + 1).map(|e| e - 1).unwrap_or(src.len());
        let raw = &src[starts[ln]..line_end];
        let comment = comment_start(raw).map(|i| raw[i..].trim_end().to_string());

        if toks.is_empty() {
            match comment {
                Some(c) => out.push(format!(
                    "{}{}",
                    INDENT.repeat(brace + usize::from(paren > 0)),
                    c
                )),
                None => out.push(String::new()),
            }
            continue;
        }

        let leading_closers = toks
            .iter()
            .take_while(|t| matches!(t.tok, Tok::RBrace | Tok::RParen | Tok::RBracket))
            .fold((0usize, 0usize), |(b, p), t| match t.tok {
                Tok::RBrace => (b + 1, p),
                _ => (b, p + 1),
            });
        let depth = brace.saturating_sub(leading_closers.0)
            + usize::from(paren.saturating_sub(leading_closers.1) > 0);

        let mut line = INDENT.repeat(depth);
        let mut prev: Option<(&Tok, bool, bool)> = None;
        for t in toks {
            let before = prev.map(|p| p.0).or(prev_global.as_ref());
            let unary = t.tok == Tok::Minus && unary_context(before);
            let dict_open = t.tok == Tok::LBrace && opens_dict(before);
            let dict_close = t.tok == Tok::RBrace && braces.last() == Some(&true);
            if let Some((p, p_unary, p_dict)) = prev {
                if space_between(p, p_unary, p_dict, &t.tok, dict_close) {
                    line.push(' ');
                }
            }
            // الفاصلة تُوحَّد إلى الفاصلة العربية؛ بقية الرموز تُنسخ حرفيًا.
            match t.tok {
                Tok::Comma => line.push('،'),
                _ => line.push_str(&src[t.span.start..t.span.end]),
            }
            match t.tok {
                Tok::LBrace => {
                    brace += 1;
                    braces.push(dict_open);
                }
                Tok::RBrace => {
                    brace = brace.saturating_sub(1);
                    braces.pop();
                }
                Tok::LParen | Tok::LBracket => paren += 1,
                Tok::RParen | Tok::RBracket => paren = paren.saturating_sub(1),
                _ => {}
            }
            prev = Some((&t.tok, unary, dict_open));
        }
        prev_global = toks.last().map(|t| t.tok.clone());
        if let Some(c) = comment {
            line.push(' ');
            line.push_str(&c);
        }
        out.push(line);
    }

    // طيّ الأسطر الفارغة المتتالية، وحذفها من البداية والنهاية.
    let mut result: Vec<String> = Vec::new();
    for l in out {
        if l.is_empty() && result.last().is_none_or(|p: &String| p.is_empty()) {
            continue;
        }
        result.push(l);
    }
    while result.last().is_some_and(|l| l.is_empty()) {
        result.pop();
    }
    let mut s = result.join("\n");
    s.push('\n');
    s
}

/// موضع أول فرق بين النصين (لعرض «الملف يحتاج تنسيقًا» في وضع التحقق).
pub fn first_difference(a: &str, b: &str) -> Option<Span> {
    let i = a
        .char_indices()
        .zip(b.chars())
        .find(|((_, x), y)| x != y)
        .map(|((i, _), _)| i);
    match i {
        Some(i) => Some(Span::new(i, i + 1)),
        None if a.len() != b.len() => Some(Span::new(a.len().min(b.len()), a.len().min(b.len()))),
        None => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fmt(s: &str) -> String {
        format(&dhad_syntax::normalize_source(s)).unwrap()
    }

    #[test]
    fn spacing_and_indentation() {
        let src = "دالة  جمع( أ ،ب ){\nأرجع أ+ب   # المجموع\n}\n\n\n\nاطبع( جمع(١,٢) )\n";
        assert_eq!(
            fmt(src),
            "دالة جمع(أ، ب) {\n    أرجع أ + ب # المجموع\n}\n\nاطبع(جمع(١، ٢))\n"
        );
    }

    #[test]
    fn unary_minus_ranges_members_indexing() {
        assert_eq!(fmt("دع س=-٥*-  ٢\n"), "دع س = -٥ * -٢\n");
        assert_eq!(
            fmt("لكل ع في ١ .. ١٠ { اطبع( ق [ ع ] ) }\n"),
            "لكل ع في ١..١٠ { اطبع(ق[ع]) }\n"
        );
        assert_eq!(fmt("اطبع(رياضيات . جذر(٩))\n"), "اطبع(رياضيات.جذر(٩))\n");
        assert_eq!(fmt("أرجع -س\n"), "أرجع -س\n");
        assert_eq!(fmt("إذا ليس (أ و ب) {}\n"), "إذا ليس (أ و ب) {}\n");
    }

    #[test]
    fn dicts_strings_comments_and_continuations() {
        let src = "دع ط = {\n\"اسم\" :\"ليلى\"،\n  \"عمر\":١٧\n}\nاطبع(\"# ليس تعليقًا\" ,\n١)\n";
        assert_eq!(
            fmt(src),
            "دع ط = {\n    \"اسم\": \"ليلى\"،\n    \"عمر\": ١٧\n}\nاطبع(\"# ليس تعليقًا\"،\n    ١)\n"
        );
    }

    #[test]
    fn dict_literals_hug_braces_blocks_do_not() {
        assert_eq!(fmt("دع ط = { \"أ\": ١ }\n"), "دع ط = {\"أ\": ١}\n");
        assert_eq!(
            fmt("لكل م في { \"أ\": ١ } {اطبع(م)}\n"),
            "لكل م في {\"أ\": ١} { اطبع(م) }\n"
        );
        assert_eq!(
            fmt("اطبع([١، {\"ع\": صحيح}])\n"),
            "اطبع([١، {\"ع\": صحيح}])\n"
        );
        assert_eq!(fmt("دالة ف() { أرجع {} }\n"), "دالة ف() { أرجع {} }\n");
    }

    #[test]
    fn interpolation_survives_reindentation() {
        assert_eq!(
            fmt("إذا صحيح {\nاطبع(\"${س}: ممتاز\")\n}\n"),
            "إذا صحيح {\n    اطبع(\"${س}: ممتاز\")\n}\n"
        );
    }

    #[test]
    fn idempotent_on_its_own_output() {
        let src =
            "إذا س>١{اطبع(\"أ\")}وإلا إذا س>٠ {\nاطبع(\"ب\")\n} وإلا {\n# تعليق\nاطبع(\"ج\")\n}\n";
        let once = fmt(src);
        assert_eq!(fmt(&once), once);
    }

    #[test]
    fn lexical_errors_are_reported() {
        assert_eq!(format("اطبع(\"غير مغلق").unwrap_err().code, 3);
    }
}
