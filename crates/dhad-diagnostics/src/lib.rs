//! نظام التشخيص للغة ضاد.
//!
//! كل خطأ أو تحذير يحمل كودًا بصيغة `ضاد-XXXX` ضمن النطاقات التالية:
//! - 0001–0999: أخطاء التحليل اللغوي والنحوي
//! - 1000–1999: أخطاء دلالية وأنواع
//! - 2000–2999: أخطاء وقت التشغيل
//! - 3000–3999: تحذيرات المدقق
//!
//! صفحات التوثيق الكاملة لكل كود في `docs/errors/`، وهي نفسها مصدر المعرفة
//! الذي تُغذّى به طبقة شرح الأخطاء الذكية.

use std::fmt;

/// موقع في النص المصدري (إزاحات بالبايت على النص المطبَّع NFC).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Hash)]
pub struct Span {
    pub start: usize,
    pub end: usize,
}

impl Span {
    pub fn new(start: usize, end: usize) -> Self {
        Span { start, end }
    }

    pub fn merge(self, other: Span) -> Span {
        Span {
            start: self.start.min(other.start),
            end: self.end.max(other.end),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Severity {
    Error,
    Warning,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Diagnostic {
    pub code: u16,
    pub severity: Severity,
    pub message: String,
    pub help: Option<String>,
    pub span: Option<Span>,
}

impl Diagnostic {
    pub fn error(code: u16, message: impl Into<String>) -> Self {
        Diagnostic {
            code,
            severity: Severity::Error,
            message: message.into(),
            help: lookup(code).map(|e| e.help.to_string()),
            span: None,
        }
    }

    pub fn warning(code: u16, message: impl Into<String>) -> Self {
        Diagnostic {
            severity: Severity::Warning,
            ..Diagnostic::error(code, message)
        }
    }

    pub fn with_span(mut self, span: Span) -> Self {
        self.span = Some(span);
        self
    }

    pub fn with_help(mut self, help: impl Into<String>) -> Self {
        self.help = Some(help.into());
        self
    }

    /// الصيغة المعروضة للكود، مثل `ضاد-1003`.
    pub fn code_str(&self) -> String {
        format!("ضاد-{:04}", self.code)
    }
}

impl fmt::Display for Diagnostic {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let kind = match self.severity {
            Severity::Error => "خطأ",
            Severity::Warning => "تحذير",
        };
        write!(f, "{kind}[{}]: {}", self.code_str(), self.message)
    }
}

impl std::error::Error for Diagnostic {}

/// مدخل في فهرس الأخطاء الموثَّق.
pub struct CatalogEntry {
    pub code: u16,
    pub title: &'static str,
    pub help: &'static str,
    pub explanation: &'static str,
}

/// الفهرس المدمج. النسخة الموسّعة لكل كود في `docs/errors/<code>.md`.
pub static CATALOG: &[CatalogEntry] = &[
    CatalogEntry { code: 1, title: "رمز غير متوقع", help: "راجع الرمز المتوقع في هذا الموضع.", explanation: "وجد المحلل رمزًا لا تسمح به قواعد اللغة في هذا الموضع. غالبًا ما يكون السبب نسيان قوس أو فاصلة أو كتابة كلمة مفتاحية في مكان خاطئ." },
    CatalogEntry { code: 2, title: "قوس غير مغلق", help: "أغلق القوس المفتوح قبل نهاية الملف.", explanation: "فُتح قوس ( أو [ أو { ولم يُغلق. يشير الخطأ إلى موضع القوس المفتوح." },
    CatalogEntry { code: 3, title: "نص غير مغلق", help: "أضف علامة الاقتباس الختامية \".", explanation: "بدأ نص بعلامة اقتباس ولم ينتهِ قبل نهاية السطر أو الملف." },
    CatalogEntry { code: 4, title: "معرّف يخلط محارف من نصوص مختلفة", help: "استخدم محارف عربية فقط أو لاتينية فقط في المعرّف الواحد.", explanation: "خلط أحرف عربية ولاتينية متشابهة بصريًا في اسم واحد يسبب أخطاء يصعب اكتشافها (UTS #39)، لذلك ترفضه اللغة." },
    CatalogEntry { code: 5, title: "كلمة مفتاحية مستخدمة كاسم", help: "اختر اسمًا آخر؛ هذه الكلمة محجوزة للغة.", explanation: "الكلمات مثل دع، إذا، طالما، دالة محجوزة ولا يمكن استخدامها كأسماء متغيرات أو دوال." },
    CatalogEntry { code: 6, title: "عدد غير صالح", help: "تأكد من صيغة العدد؛ الفاصلة العشرية الصحيحة هي . أو ٫", explanation: "تعذّر قراءة العدد. يُقبل في العدد الواحد أرقام عربية شرقية أو غربية مع فاصلة عشرية واحدة." },
    CatalogEntry { code: 1001, title: "متغير غير معرَّف", help: "عرّف المتغير بـ «دع» قبل استخدامه، أو تحقق من التهجئة.", explanation: "استُخدم اسم لم يُعرَّف في هذا النطاق أو في أي نطاق أعلى. تحقق من التهجئة (الهمزات والتاء المربوطة) ومن أن التعريف يسبق الاستخدام." },
    CatalogEntry { code: 1002, title: "إعادة تعيين ثابت", help: "الثوابت لا تتغير؛ استخدم «دع» إن أردت قيمة قابلة للتغيير.", explanation: "القيم المعرَّفة بـ «ثابت» لا يمكن تعديلها بعد تعريفها." },
    CatalogEntry { code: 1003, title: "لا يمكن جمع نص مع عدد", help: "حوّل العدد إلى نص بـ نص(العدد)، أو استخدم دمج النصوص \"${...}\".", explanation: "العملية + تعمل بين عددين (جمع حسابي) أو بين نصين (ضم). الجمع بين نص وعدد غامض، لذلك ترفضه اللغة وتطلب تحويلًا صريحًا." },
    CatalogEntry { code: 1004, title: "عدد المعاملات لا يطابق تعريف الدالة", help: "راجع توقيع الدالة وعدد معاملاتها.", explanation: "استُدعيت دالة بعدد معاملات مختلف عما عُرِّفت به." },
    CatalogEntry { code: 1005, title: "استدعاء قيمة ليست دالة", help: "تحقق من أن الاسم يشير إلى دالة لا إلى متغير عادي.", explanation: "استُخدمت أقواس الاستدعاء ( ) بعد قيمة ليست دالة." },
    CatalogEntry { code: 1006, title: "«أرجع» خارج دالة", help: "انقل الجملة داخل دالة أو احذفها.", explanation: "جملة «أرجع» لا معنى لها إلا داخل جسم دالة." },
    CatalogEntry { code: 1007, title: "«توقف» أو «استمر» خارج حلقة", help: "تُستخدم هاتان الكلمتان داخل «طالما» أو «لكل» فقط.", explanation: "جملتا التحكم في الحلقات لا معنى لهما خارج حلقة." },
    CatalogEntry { code: 1008, title: "مقارنة بين نوعين غير متوافقين", help: "حوّل أحد الطرفين إلى نوع الآخر قبل المقارنة.", explanation: "عمليات < و > و <= و >= تعمل بين عددين أو بين نصين فقط." },
    CatalogEntry { code: 1009, title: "وحدة غير موجودة", help: "الوحدات المتاحة: رياضيات، نصوص، قوائم، وقت، عشوائي.", explanation: "طلب الاستيراد وحدة غير معروفة للمكتبة القياسية." },
    CatalogEntry { code: 1010, title: "الشرط ليس قيمة منطقية", help: "استخدم مقارنة صريحة مثل: س != ٠ أو طول(القائمة) > ٠", explanation: "شروط «إذا» و«طالما» تقبل فقط صحيح أو خطأ. لا تُعامل الأعداد أو النصوص كقيم منطقية ضمنيًا، لتجنب التباس المبتدئين." },
    CatalogEntry { code: 1011, title: "العملية غير معرَّفة لهذين النوعين", help: "راجع أنواع الطرفين؛ استخدم نوع(القيمة) لمعرفة النوع.", explanation: "طُبِّقت عملية حسابية أو منطقية على أنواع لا تدعمها." },
    CatalogEntry { code: 1012, title: "لا يمكن الإسناد إلى هذا الهدف", help: "الإسناد يكون إلى متغير أو عنصر قائمة أو مفتاح قاموس.", explanation: "الطرف الأيسر من = يجب أن يكون مكانًا قابلًا للكتابة." },
    CatalogEntry { code: 2001, title: "قسمة على صفر", help: "تحقق من المقسوم عليه قبل القسمة.", explanation: "القسمة أو باقي القسمة على صفر غير معرَّفة رياضيًا." },
    CatalogEntry { code: 2002, title: "فهرس خارج حدود القائمة", help: "الفهارس تبدأ من ٠ وتنتهي عند طول(القائمة) - ١.", explanation: "حاولت الوصول إلى عنصر بفهرس أكبر من أو يساوي طول القائمة أو أصغر من صفر." },
    CatalogEntry { code: 2003, title: "مفتاح غير موجود في القاموس", help: "تحقق بـ «المفتاح في القاموس» قبل الوصول.", explanation: "طُلب مفتاح غير موجود في القاموس." },
    CatalogEntry { code: 2004, title: "تجاوز عمق الاستدعاء", help: "تحقق من شرط التوقف في الدالة ذاتية الاستدعاء.", explanation: "استدعت الدالة نفسها مرات كثيرة جدًا دون الوصول إلى حالة أساس." },
    CatalogEntry { code: 2005, title: "تجاوز حد التنفيذ", help: "ربما توجد حلقة لا تنتهي؛ تحقق من شرط الحلقة.", explanation: "نفّذ البرنامج خطوات أكثر من الحد المسموح به في هذا الوضع (عدّاد الوقود)." },
    CatalogEntry { code: 2006, title: "فشل التأكيد", help: "القيمة المتوقعة لم تتحقق؛ راجع منطق الاختبار.", explanation: "تأكد(...) استُدعيت بقيمة خطأ." },
    CatalogEntry { code: 2007, title: "نوع غير متوقع", help: "راجع نوع القيمة الممررة؛ استخدم نوع(القيمة).", explanation: "مرّرت قيمة من نوع لا تقبله هذه الدالة أو العملية." },
    CatalogEntry { code: 2008, title: "تعذّر تحويل النص إلى عدد", help: "تأكد من أن النص يحتوي أرقامًا فقط (عربية أو غربية).", explanation: "دالة عدد(...) تلقّت نصًا لا يمثل عددًا صالحًا." },
    CatalogEntry { code: 3001, title: "متغير معرَّف وغير مستخدم", help: "احذفه أو استخدمه.", explanation: "تحذير من المدقق: عُرِّف المتغير ولم يُقرأ في أي مكان." },
    CatalogEntry { code: 3002, title: "معرّفان متشابهان", help: "وحّد التهجئة لتجنب الالتباس.", explanation: "تحذير: يوجد معرّفان لا يختلفان إلا بالهمزة أو التاء المربوطة/الهاء." },
    CatalogEntry { code: 3003, title: "تشكيل داخل معرّف", help: "احذف الحركات من أسماء المتغيرات.", explanation: "تحذير: الحركات تُتجاهل في المعرّفات؛ «عَدد» و«عدد» الاسم نفسه." },
    CatalogEntry { code: 4001, title: "بنية غير مدعومة في مولّد WebAssembly", help: "شغّل البرنامج بالمفسر، أو اقتصر على الأعداد الصحيحة والقيم المنطقية والدوال والشروط والحلقات على المدى.", explanation: "مولّد WebAssembly يترجم حاليًا مجموعة فرعية عددية من اللغة. البرنامج يستخدم بنية خارجها (مثل القوائم أو الأعداد العشرية أو الوحدات)." },
    CatalogEntry { code: 4002, title: "نوع غير متوافق في مولّد WebAssembly", help: "اجعل المتغير يحتفظ بنوع واحد طوال البرنامج.", explanation: "المولّد يستنتج نوعًا ثابتًا لكل متغير ودالة. تغيير نوع متغير (عدد ثم منطقي مثلًا) يمنع الترجمة." },
];

pub fn lookup(code: u16) -> Option<&'static CatalogEntry> {
    CATALOG.iter().find(|e| e.code == code)
}

/// تحويل الأرقام الغربية في نص إلى أرقام عربية شرقية.
pub fn to_eastern_digits(s: &str) -> String {
    s.chars()
        .map(|c| match c {
            '0'..='9' => char::from_u32(0x0660 + (c as u32 - '0' as u32)).unwrap(),
            _ => c,
        })
        .collect()
}

/// السطر والعمود (ابتداءً من 1، العمود بالمحارف لا بالبايتات).
pub fn line_col(source: &str, offset: usize) -> (usize, usize) {
    let offset = offset.min(source.len());
    let before = &source[..offset];
    let line = before.matches('\n').count() + 1;
    let line_start = before.rfind('\n').map(|i| i + 1).unwrap_or(0);
    let col = source[line_start..offset].chars().count() + 1;
    (line, col)
}

/// عرض التشخيص بصيغة مقروءة مع سطر المصدر وموضع الخطأ.
pub fn render(diag: &Diagnostic, source: &str, filename: &str) -> String {
    let mut out = String::new();
    out.push_str(&diag.to_string());
    out.push('\n');

    if let Some(span) = diag.span {
        let (line, col) = line_col(source, span.start);
        out.push_str(&format!(
            "  ← الملف: {filename} — السطر {line}، العمود {col}\n"
        ));
        let line_start = source[..span.start.min(source.len())]
            .rfind('\n')
            .map(|i| i + 1)
            .unwrap_or(0);
        let line_end = source[line_start..]
            .find('\n')
            .map(|i| line_start + i)
            .unwrap_or(source.len());
        let text = &source[line_start..line_end];
        let gutter = format!("{line}");
        let pad = " ".repeat(gutter.len());
        out.push_str(&format!("{pad} │\n"));
        out.push_str(&format!("{gutter} │ {text}\n"));
        let before = source[line_start..span.start.min(line_end)].chars().count();
        let width = source[span.start.min(line_end)..span.end.min(line_end)]
            .chars()
            .count()
            .max(1);
        out.push_str(&format!(
            "{pad} │ {}{}\n",
            " ".repeat(before),
            "^".repeat(width)
        ));
    }

    if let Some(help) = &diag.help {
        out.push_str(&format!("  = مساعدة: {help}\n"));
    }
    if lookup(diag.code).is_some() {
        out.push_str(&format!(
            "  = لمزيد من التفاصيل: ضاد شرح {:04}\n",
            diag.code
        ));
    }
    out
}

/// نص «ضاد شرح <code>»: الشرح الكامل من الفهرس.
pub fn explain(code: u16) -> Option<String> {
    lookup(code).map(|e| {
        format!(
            "ضاد-{:04}: {}\n\n{}\n\nمساعدة: {}\n\nالتوثيق الكامل: docs/errors/{:04}.md\n",
            e.code, e.title, e.explanation, e.help, e.code
        )
    })
}

/// نص JSON مهرَّب.
pub fn json_str(s: &str) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

/// إزاحة UTF-16 (وحدة المواضع في محررات المتصفح) لإزاحة بايت.
fn utf16_offset(src: &str, byte: usize) -> usize {
    src[..byte.min(src.len())].encode_utf16().count()
}

/// تمثيل JSON للتشخيص، بمواضع UTF-16 (وحدة المواضع في المحررات وJavaScript).
pub fn to_json(d: &Diagnostic, src: &str) -> String {
    let mut fields = vec![
        format!("\"code\":{}", d.code),
        format!("\"codeStr\":{}", json_str(&d.code_str())),
        format!(
            "\"severity\":{}",
            json_str(match d.severity {
                Severity::Error => "error",
                Severity::Warning => "warning",
            })
        ),
        format!("\"message\":{}", json_str(&d.message)),
        format!("\"rendered\":{}", json_str(&render(d, src, "البرنامج.ضاد"))),
    ];
    if let Some(h) = &d.help {
        fields.push(format!("\"help\":{}", json_str(h)));
    }
    if let Some(e) = lookup(d.code) {
        fields.push(format!("\"title\":{}", json_str(e.title)));
        fields.push(format!("\"explanation\":{}", json_str(e.explanation)));
    }
    if let Some(span) = d.span {
        let (line, col) = line_col(src, span.start);
        fields.push(format!("\"line\":{line},\"col\":{col}"));
        fields.push(format!(
            "\"from\":{},\"to\":{}",
            utf16_offset(src, span.start),
            utf16_offset(src, span.end)
        ));
    }
    format!("{{{}}}", fields.join(","))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn code_formatting() {
        let d = Diagnostic::error(1003, "x");
        assert_eq!(d.code_str(), "ضاد-1003");
        assert!(d.help.is_some());
    }

    #[test]
    fn line_and_column_count_chars() {
        let src = "دع س = ١\nدع ص = \"نص\" + ٢";
        let idx = src.find('+').unwrap();
        assert_eq!(line_col(src, idx), (2, 13));
    }

    #[test]
    fn eastern_digits() {
        assert_eq!(to_eastern_digits("1003"), "١٠٠٣");
    }

    #[test]
    fn render_contains_pointer() {
        let src = "دع س = \"أ\" + ١";
        let d = Diagnostic::error(1003, "لا يمكن جمع نص مع عدد")
            .with_span(Span::new(src.find('"').unwrap(), src.len()));
        let r = render(&d, src, "مثال.ضاد");
        assert!(r.contains("ضاد-1003"));
        assert!(r.contains("^"));
        assert!(r.contains("ضاد شرح 1003"));
    }
}
