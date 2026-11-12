// تعريف لغة ضاد للمحرر: الكلمات المفتاحية، الدوال المدمجة، الوحدات، والمُرمِّز.
import { StreamLanguage, HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";

export const KEYWORDS = [
  ["دع", "تعريف متغير: دع س = ١"],
  ["ثابت", "تعريف ثابت لا يتغير: ثابت ط = ٣٫١٤"],
  ["إذا", "تفرع شرطي: إذا شرط { ... }"],
  ["وإلا", "الفرع البديل: وإلا { ... } أو وإلا إذا ..."],
  ["طالما", "حلقة شرطية: طالما شرط { ... }"],
  ["لكل", "حلقة تكرار: لكل ع في ١..١٠ { ... }"],
  ["في", "تُستخدم مع لكل، وللفحص: ع في القائمة"],
  ["دالة", "تعريف دالة: دالة اسم(أ، ب) { ... }"],
  ["أرجع", "إرجاع قيمة من دالة"],
  ["توقف", "الخروج من الحلقة"],
  ["استمر", "الانتقال إلى الدورة التالية"],
  ["صحيح", "القيمة المنطقية: صحيح"],
  ["خطأ", "القيمة المنطقية: خطأ"],
  ["و", "العطف المنطقي: أ و ب"],
  ["أو", "الفصل المنطقي: أ أو ب"],
  ["ليس", "النفي المنطقي: ليس أ"],
  ["عدم", "غياب القيمة"],
  ["استورد", "استيراد وحدة: استورد رياضيات"],
  ["اختبر", "كتلة اختبار: اختبر \"وصف\" { تأكد(...) }"],
];

export const BUILTINS = [
  ["اطبع", "اطبع(قيمة، ...)", "طباعة القيم في المخرجات"],
  ["نص", "نص(قيمة)", "تحويل قيمة إلى نص"],
  ["عدد", "عدد(نص)", "تحويل نص إلى عدد (يقبل الأرقام العربية والغربية)"],
  ["طول", "طول(قيمة)", "طول نص أو قائمة أو قاموس"],
  ["نوع", "نوع(قيمة)", "اسم نوع القيمة"],
  ["مدى", "مدى(من، إلى)", "مدى أعداد نصف مفتوح"],
  ["أضف", "أضف(قائمة، عنصر)", "إضافة عنصر إلى نهاية قائمة"],
  ["احذف", "احذف(قائمة، فهرس)", "حذف عنصر وإرجاعه"],
  ["اقرأ", "اقرأ(رسالة)", "قراءة سطر من المستخدم"],
  ["تأكد", "تأكد(شرط، رسالة)", "التأكد من صحة شرط داخل الاختبارات"],
  ["أكبر", "أكبر(قيم...)", "أكبر قيمة"],
  ["أصغر", "أصغر(قيم...)", "أصغر قيمة"],
  ["مطلق", "مطلق(عدد)", "القيمة المطلقة"],
  ["تقريب", "تقريب(عدد، خانات)", "تقريب عدد"],
  ["جذر", "جذر(عدد)", "الجذر التربيعي"],
];

export const MODULES = {
  "رياضيات": ["جذر", "قوة", "مطلق", "تقريب", "سقف", "أرضية", "أكبر", "أصغر", "ط", "هـ"],
  "نصوص": ["قسّم", "اربط", "استبدل", "يبدأ_بـ", "ينتهي_بـ", "يحتوي", "احذف_التشكيل", "طبّع", "اقلب", "قصّ"],
  "قوائم": ["رتّب", "اعكس", "اجمع", "أضف", "احذف", "يحتوي"],
  "وقت": ["الآن", "انتظر"],
  "عشوائي": ["عدد_عشوائي", "اختر"],
};

const KW = new Set(KEYWORDS.map(([k]) => k).concat(["اذا", "والا", "ارجع", "خطا", "او"]));
const BI = new Set(BUILTINS.map(([b]) => b));
const MOD = new Set(Object.keys(MODULES));

const IDENT = /^[\p{L}_][\p{L}\p{N}\p{M}_]*[؟?]?/u;
const NUMBER = /^[0-9٠-٩۰-۹][0-9٠-٩۰-۹_]*(?:[.٫][0-9٠-٩۰-۹]+)?/u;

export const dhadLanguage = StreamLanguage.define({
  name: "dhad",
  startState: () => ({ inString: null }),
  token(stream, state) {
    if (state.inString) {
      while (!stream.eol()) {
        if (stream.match("${")) { stream.backUp(2); if (stream.pos > stream.start) return "string"; stream.match("${"); state.interp = true; state.inString2 = state.inString; state.inString = null; return "brace"; }
        const ch = stream.next();
        if (ch === "\\") { stream.next(); continue; }
        if (ch === state.inString) { state.inString = null; return "string"; }
      }
      return "string";
    }
    if (state.interp && stream.peek() === "}") {
      stream.next(); state.interp = false; state.inString = state.inString2; return "brace";
    }
    if (stream.eatSpace()) return null;
    if (stream.peek() === "#") { stream.skipToEnd(); return "comment"; }
    const ch = stream.peek();
    if (ch === '"' || ch === "«") {
      stream.next(); state.inString = ch === '"' ? '"' : "»";
      return "string";
    }
    if (stream.match(NUMBER)) return "number";
    const m = stream.match(IDENT);
    if (m) {
      const w = m[0].replace(/[ً-ٰٟـ]/g, "");
      if (KW.has(w)) return w === "صحيح" || w === "خطأ" || w === "عدم" ? "atom" : "keyword";
      if (BI.has(w)) return "builtin";
      if (MOD.has(w)) return "namespace";
      if (stream.peek() === "(") return "function";
      return "variableName";
    }
    if (stream.match(/^(==|!=|<=|>=|\/\/|\.\.|[-+*/%<>=×÷≠≤≥])/)) return "operator";
    stream.next();
    return "punctuation";
  },
  languageData: { commentTokens: { line: "#" }, closeBrackets: { brackets: ["(", "[", "{", '"', "«"] } },
  tokenTable: { builtin: t.standard(t.variableName), namespace: t.namespace, function: t.function(t.variableName), brace: t.special(t.brace) },
});

export const dhadHighlight = syntaxHighlighting(HighlightStyle.define([
  { tag: t.keyword, color: "var(--tk-keyword)", fontWeight: "700" },
  { tag: t.atom, color: "var(--tk-atom)", fontWeight: "600" },
  { tag: t.string, color: "var(--tk-string)" },
  { tag: t.number, color: "var(--tk-number)" },
  { tag: t.comment, color: "var(--tk-comment)", fontStyle: "italic" },
  { tag: t.standard(t.variableName), color: "var(--tk-builtin)", fontWeight: "600" },
  { tag: t.namespace, color: "var(--tk-namespace)", fontWeight: "600" },
  { tag: t.function(t.variableName), color: "var(--tk-function)" },
  { tag: t.operator, color: "var(--tk-operator)" },
  { tag: t.special(t.brace), color: "var(--tk-keyword)", fontWeight: "700" },
]));
