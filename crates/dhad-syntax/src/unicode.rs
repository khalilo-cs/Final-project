//! سياسة Unicode للغة ضاد (انظر ADR-0002).
//!
//! - النص المصدري يُطبَّع إلى NFC قبل أي معالجة.
//! - الحركات (التشكيل) والكشيدة تُتجاهل داخل المعرّفات.
//! - الأرقام العربية الشرقية (٠-٩ و ۰-۹) والغربية (0-9) مقبولتان معًا.
//! - خلط أحرف عربية ولاتينية في معرّف واحد مرفوض (حماية من المحارف المربكة).

use unicode_normalization::UnicodeNormalization;

/// تطبيع النص المصدري إلى NFC.
pub fn normalize_source(src: &str) -> String {
    src.nfc().collect()
}

/// الحركات والعلامات العربية التي تُتجاهل في المعرّفات، بما فيها الكشيدة (ـ).
pub fn is_tashkeel(c: char) -> bool {
    matches!(
        c,
        '\u{0610}'..='\u{061A}'
            | '\u{064B}'..='\u{065F}'
            | '\u{0670}'
            | '\u{06D6}'..='\u{06DC}'
            | '\u{06DF}'..='\u{06E4}'
            | '\u{06E7}'
            | '\u{06E8}'
            | '\u{06EA}'..='\u{06ED}'
            | '\u{0640}'
    )
}

pub fn strip_tashkeel(s: &str) -> String {
    s.chars().filter(|c| !is_tashkeel(*c)).collect()
}

/// قيمة الرقم إن كان المحرف رقمًا عربيًا شرقيًا أو غربيًا.
pub fn digit_value(c: char) -> Option<u32> {
    match c {
        '0'..='9' => Some(c as u32 - '0' as u32),
        '\u{0660}'..='\u{0669}' => Some(c as u32 - 0x0660),
        '\u{06F0}'..='\u{06F9}' => Some(c as u32 - 0x06F0),
        _ => None,
    }
}

pub fn is_digit(c: char) -> bool {
    digit_value(c).is_some()
}

/// الفاصلة العشرية: النقطة أو الفاصلة العشرية العربية (٫).
pub fn is_decimal_point(c: char) -> bool {
    c == '.' || c == '\u{066B}'
}

/// فاصل المعاملات: الفاصلة اللاتينية أو العربية (،).
pub fn is_comma(c: char) -> bool {
    c == ',' || c == '\u{060C}'
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Script {
    Arabic,
    Latin,
    Other,
}

pub fn script_of(c: char) -> Script {
    match c {
        '\u{0600}'..='\u{06FF}'
        | '\u{0750}'..='\u{077F}'
        | '\u{08A0}'..='\u{08FF}'
        | '\u{FB50}'..='\u{FDFF}'
        | '\u{FE70}'..='\u{FEFF}' => Script::Arabic,
        'a'..='z' | 'A'..='Z' | '\u{00C0}'..='\u{024F}' => Script::Latin,
        _ => Script::Other,
    }
}

pub fn is_ident_start(c: char) -> bool {
    (c.is_alphabetic() && !is_tashkeel(c)) || c == '_'
}

pub fn is_ident_continue(c: char) -> bool {
    c.is_alphanumeric() || c == '_' || is_tashkeel(c) || is_digit(c)
}

/// هل يخلط المعرّف أحرفًا عربية ولاتينية معًا؟
pub fn mixes_scripts(ident: &str) -> bool {
    let mut arabic = false;
    let mut latin = false;
    for c in ident.chars() {
        match script_of(c) {
            Script::Arabic if c.is_alphabetic() => arabic = true,
            Script::Latin => latin = true,
            _ => {}
        }
    }
    arabic && latin
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strips_harakat_and_tatweel() {
        assert_eq!(strip_tashkeel("عَدَدٌ"), "عدد");
        assert_eq!(strip_tashkeel("عــدد"), "عدد");
    }

    #[test]
    fn digits_both_scripts() {
        assert_eq!(digit_value('٣'), Some(3));
        assert_eq!(digit_value('3'), Some(3));
        assert_eq!(digit_value('۷'), Some(7));
        assert_eq!(digit_value('x'), None);
    }

    #[test]
    fn detects_mixed_scripts() {
        assert!(mixes_scripts("عددx"));
        assert!(!mixes_scripts("عدد_١"));
        assert!(!mixes_scripts("total_1"));
    }
}
