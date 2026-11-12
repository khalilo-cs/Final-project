//! المحلل اللغوي والنحوي للغة ضاد.
//!
//! مسار التحليل: نص مصدري → تطبيع Unicode (NFC) → رموز (lexer) → شجرة البرنامج (parser).
//!
//! ملاحظة معمارية: هذا المحلل اليدوي (recursive descent) هو النواة المرجعية
//! للدلالات. قواعد Tree-sitter في `grammar/` تُستخدم للمحرر وخادم اللغة،
//! واختبارات corpus تضمن تطابق الاثنين.

pub mod ast;
pub mod lexer;
pub mod parser;
pub mod unicode;

pub use ast::*;
pub use dhad_diagnostics::{Diagnostic, Span};
pub use lexer::{tokenize, Kw, StrPart, Tok, Token};
pub use parser::{parse, parse_expression};
pub use unicode::normalize_source;
