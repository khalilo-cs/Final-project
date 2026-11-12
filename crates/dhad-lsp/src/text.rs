//! التحويل بين إزاحات البايت ومواضع LSP (سطر + عمود بوحدات UTF-16).

use lsp_types::Position;

pub struct LineIndex {
    /// إزاحة بداية كل سطر بالبايت.
    starts: Vec<usize>,
}

impl LineIndex {
    pub fn new(text: &str) -> Self {
        let mut starts = vec![0];
        starts.extend(text.match_indices('\n').map(|(i, _)| i + 1));
        LineIndex { starts }
    }

    pub fn position(&self, text: &str, offset: usize) -> Position {
        let offset = offset.min(text.len());
        let line = self.starts.partition_point(|&s| s <= offset) - 1;
        let col = text[self.starts[line]..offset].encode_utf16().count();
        Position::new(line as u32, col as u32)
    }

    pub fn offset(&self, text: &str, pos: Position) -> usize {
        let Some(&start) = self.starts.get(pos.line as usize) else {
            return text.len();
        };
        let end = self
            .starts
            .get(pos.line as usize + 1)
            .map(|e| e - 1)
            .unwrap_or(text.len());
        let mut units = 0u32;
        for (i, c) in text[start..end].char_indices() {
            if units >= pos.character {
                return start + i;
            }
            units += c.len_utf16() as u32;
        }
        end
    }
}

pub fn is_ident_char(c: char) -> bool {
    dhad_syntax::unicode::is_ident_continue(c) || c == '؟'
}

/// المعرّف الذي يقع عليه الموضع، مع مداه بالبايت.
pub fn ident_at(text: &str, offset: usize) -> Option<(String, (usize, usize))> {
    let offset = offset.min(text.len());
    let start = text[..offset]
        .char_indices()
        .rev()
        .take_while(|(_, c)| is_ident_char(*c))
        .last()
        .map(|(i, _)| i)
        .unwrap_or(offset);
    let end = offset
        + text[offset..]
            .char_indices()
            .take_while(|(_, c)| is_ident_char(*c))
            .last()
            .map(|(i, c)| i + c.len_utf8())
            .unwrap_or(0);
    (start < end).then(|| (text[start..end].to_string(), (start, end)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn roundtrip_arabic_positions() {
        let t = "دع س = ١\nاطبع(س)\n";
        let idx = LineIndex::new(t);
        let off = t.rfind('س').unwrap();
        let p = idx.position(t, off);
        assert_eq!(p, Position::new(1, 5));
        assert_eq!(idx.offset(t, p), off);
    }

    #[test]
    fn ident_under_cursor() {
        let t = "اطبع(المجموع)";
        let off = t.find("مجموع").unwrap();
        assert_eq!(ident_at(t, off).unwrap().0, "المجموع");
    }
}
