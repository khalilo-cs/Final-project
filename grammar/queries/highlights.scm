; تلوين لغة ضاد

(comment) @comment
(string) @string
(string_content) @string
(escape_sequence) @string.escape
(interpolation "${" @punctuation.special "}" @punctuation.special)
(number) @number
[(true) (false)] @boolean
(null) @constant.builtin

[
  "دع" "ثابت" "إذا" "اذا" "وإلا" "والا" "طالما" "لكل" "في"
  "دالة" "دالّة" "أرجع" "ارجع" "استورد" "اختبر"
] @keyword
(break_statement) @keyword
(continue_statement) @keyword
["و" "أو" "او" "ليس"] @keyword.operator

(function_declaration name: (identifier) @function)
(parameters (identifier) @variable.parameter)
(call_expression function: (identifier) @function.call)
(call_expression function: (member_expression property: (identifier) @function.method.call))
(member_expression property: (identifier) @property)
(pair key: (string) @property)
(import_statement module: (identifier) @module)
(const_declaration name: (identifier) @constant)

((identifier) @function.builtin
  (#any-of? @function.builtin
    "اطبع" "نص" "عدد" "طول" "نوع" "مدى" "أضف" "احذف" "اقرأ" "تأكد"
    "أكبر" "أصغر" "مطلق" "تقريب" "جذر"))

((identifier) @module.builtin
  (#any-of? @module.builtin "رياضيات" "نصوص" "قوائم" "وقت" "عشوائي"))

(identifier) @variable

["=" "==" "!=" "≠" "<" ">" "<=" ">=" "≤" "≥" "+" "-" "−" "*" "/" "//" "%" "×" "÷" "٪" ".."] @operator
["(" ")" "[" "]" "{" "}"] @punctuation.bracket
["," "،" ":" "." ";" "؛"] @punctuation.delimiter
