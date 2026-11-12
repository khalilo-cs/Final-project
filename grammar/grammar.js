/**
 * @file قواعد Tree-sitter للغة ضاد
 * @license MIT
 *
 * المحلل المرجعي للدلالات هو `crates/dhad-syntax`. هذه القواعد تخدم المحررات:
 * تحليل تزايدي، تلوين دقيق، وشجرة متاحة حتى مع وجود أخطاء أثناء الكتابة.
 */

/// <reference types="tree-sitter-cli/dsl" />
// @ts-check

const PREC = {
  or: 1,
  and: 2,
  equality: 3,
  compare: 4,
  range: 5,
  additive: 6,
  multiplicative: 7,
  unary: 8,
  postfix: 9,
};

const DIGIT = "0-9\u0660-\u0669\u06F0-\u06F9";

/** @param {string[]} words */
const kw = (...words) => (words.length === 1 ? words[0] : choice(...words));

const comma = choice(",", "،");

/**
 * @param {RuleOrLiteral} rule
 * @param {RuleOrLiteral} sep
 */
const sepBy1 = (sep, rule) => seq(rule, repeat(seq(sep, rule)));

module.exports = grammar({
  name: "dhad",

  word: ($) => $.identifier,

  // الكلمات المحجوزة لا تصلح أسماءً في أي موضع (يطابق رفض المحلل المرجعي: ضاد-0005).
  reserved: {
    global: (_) => [
      "دع", "ثابت", "إذا", "اذا", "وإلا", "والا", "طالما", "لكل", "في", "دالة", "دالّة",
      "أرجع", "ارجع", "توقف", "استمر", "صحيح", "خطأ", "خطا", "و", "أو", "او", "ليس",
      "عدم", "استورد", "اختبر",
    ],
  },

  extras: ($) => [/[ \t\r\u200E\u200F\uFEFF]/, $.comment],

  conflicts: ($) => [[$.if_statement]],

  supertypes: ($) => [$._statement, $._expression],

  rules: {
    source_file: ($) =>
      seq(
        optional($._terminator),
        optional(seq(sepBy1($._terminator, $._statement), optional($._terminator))),
      ),

    _terminator: (_) => prec.right(repeat1(choice("\n", ";", "؛"))),

    _statement: ($) =>
      choice(
        $.let_declaration,
        $.const_declaration,
        $.assignment,
        $.if_statement,
        $.while_statement,
        $.for_statement,
        $.function_declaration,
        $.return_statement,
        $.break_statement,
        $.continue_statement,
        $.import_statement,
        $.test_block,
        $.expression_statement,
      ),

    let_declaration: ($) =>
      seq(
        kw("دع"),
        field("name", $.identifier),
        optional(seq(":", field("type", $.identifier))),
        "=",
        field("value", $._expression),
      ),

    const_declaration: ($) =>
      seq(kw("ثابت"), field("name", $.identifier), "=", field("value", $._expression)),

    assignment: ($) =>
      seq(
        field("left", choice($.identifier, $.index_expression, $.member_expression)),
        "=",
        field("right", $._expression),
      ),

    if_statement: ($) =>
      seq(
        kw("إذا", "اذا"),
        field("condition", $._expression),
        field("consequence", $.block),
        repeat(field("alternative", $.else_if_clause)),
        optional(field("alternative", $.else_clause)),
      ),

    else_if_clause: ($) =>
      seq(
        optional("\n"),
        kw("وإلا", "والا"),
        kw("إذا", "اذا"),
        field("condition", $._expression),
        field("consequence", $.block),
      ),

    else_clause: ($) => seq(optional("\n"), kw("وإلا", "والا"), field("body", $.block)),

    while_statement: ($) =>
      seq(kw("طالما"), field("condition", $._expression), field("body", $.block)),

    for_statement: ($) =>
      seq(
        kw("لكل"),
        field("variable", $.identifier),
        kw("في"),
        field("iterable", $._expression),
        field("body", $.block),
      ),

    function_declaration: ($) =>
      seq(
        kw("دالة", "دالّة"),
        field("name", $.identifier),
        field("parameters", $.parameters),
        field("body", $.block),
      ),

    parameters: ($) => seq("(", optional(seq(sepBy1(comma, $.identifier), optional(comma))), ")"),

    return_statement: ($) => prec.right(seq(kw("أرجع", "ارجع"), optional($._expression))),
    break_statement: (_) => kw("توقف"),
    continue_statement: (_) => kw("استمر"),

    import_statement: ($) =>
      seq(kw("استورد"), field("module", sepBy1(".", $.identifier))),

    test_block: ($) =>
      seq(kw("اختبر"), field("name", $.string), field("body", $.block)),

    expression_statement: ($) => $._expression,

    block: ($) =>
      seq(
        "{",
        optional($._terminator),
        optional(seq(sepBy1($._terminator, $._statement), optional($._terminator))),
        "}",
      ),

    // ---------------- التعبيرات ----------------

    _expression: ($) =>
      choice(
        $.binary_expression,
        $.unary_expression,
        $.range_expression,
        $.call_expression,
        $.index_expression,
        $.member_expression,
        $.parenthesized_expression,
        $.identifier,
        $.number,
        $.string,
        $.true,
        $.false,
        $.null,
        $.list,
        $.dictionary,
      ),

    binary_expression: ($) => {
      /** @type {[number, RuleOrLiteral][]} */
      const table = [
        [PREC.or, kw("أو", "او")],
        [PREC.and, kw("و")],
        [PREC.equality, choice("==", "!=", "≠", kw("في"))],
        [PREC.compare, choice("<", ">", "<=", ">=", "≤", "≥")],
        [PREC.additive, choice("+", "-", "−")],
        [PREC.multiplicative, choice("*", "/", "//", "%", "×", "÷", "٪")],
      ];
      return choice(
        ...table.map(([p, op]) =>
          prec.left(
            p,
            seq(field("left", $._expression), field("operator", op), field("right", $._expression)),
          ),
        ),
      );
    },

    unary_expression: ($) =>
      prec(PREC.unary, seq(field("operator", choice(kw("ليس"), "-", "−")), field("operand", $._expression))),

    range_expression: ($) =>
      prec.left(PREC.range, seq(field("start", $._expression), "..", field("end", $._expression))),

    call_expression: ($) =>
      prec(PREC.postfix, seq(field("function", $._expression), field("arguments", $.arguments))),

    arguments: ($) =>
      seq("(", optional(seq(sepBy1(seq(optional("\n"), comma), seq(optional("\n"), $._expression)), optional(comma))), optional("\n"), ")"),

    index_expression: ($) =>
      prec(PREC.postfix, seq(field("object", $._expression), "[", field("index", $._expression), "]")),

    member_expression: ($) =>
      prec(PREC.postfix, seq(field("object", $._expression), ".", field("property", $.identifier))),

    parenthesized_expression: ($) => seq("(", $._expression, ")"),

    list: ($) =>
      seq("[", optional("\n"), optional(seq(sepBy1(seq(comma, optional("\n")), $._expression), optional(comma))), optional("\n"), "]"),

    dictionary: ($) =>
      seq(
        "{",
        optional($._terminator),
        optional(seq(sepBy1(seq(comma, optional($._terminator)), $.pair), optional(comma))),
        optional($._terminator),
        "}",
      ),

    pair: ($) => seq(field("key", $._expression), ":", field("value", $._expression)),

    // ---------------- الرموز ----------------

    identifier: (_) => /[\p{L}_][\p{L}\p{N}\p{M}_]*[؟?]?/u,

    number: (_) => new RegExp(`[${DIGIT}][${DIGIT}_]*([.\\u066B][${DIGIT}]+)?`),

    string: ($) =>
      choice(
        seq(
          '"',
          repeat(choice($.string_content, alias($._lone_dollar, $.string_content), $.escape_sequence, $.interpolation)),
          token.immediate('"'),
        ),
        seq("«", optional(alias(token.immediate(prec(1, /[^»\n]+/)), $.string_content)), token.immediate("»")),
      ),

    string_content: (_) => token.immediate(prec(1, /([^"\\$\n]|\$[^{"\\\n])+/)),

    // «$» منفردة (مثل "السعر ٥$") بأولوية أدنى من «${» فيفوز الأطول.
    _lone_dollar: (_) => token.immediate("$"),

    escape_sequence: (_) => token.immediate(/\\./),

    interpolation: ($) => seq(token.immediate("${"), $._expression, "}"),

    true: (_) => kw("صحيح"),
    false: (_) => kw("خطأ", "خطا"),
    null: (_) => kw("عدم"),

    comment: (_) => token(seq("#", /.*/)),
  },
});
