// طبقة BiDi لمحرر ضاد.
//
// المشكلة: خوارزمية Unicode (UAX #9) تجعل الرموز المحايدة (= + ( ) والأرقام)
// تأخذ اتجاهها من جيرانها، فيظهر سطر مثل `دع result = مجموع + 5` مشوَّهًا.
// الحل: اتجاه أساسي RTL ثابت للمحرر، وعزل اتجاهي (isolate) لكل رمز لاتيني
// أو رقم غربي أو نص حرفي، بحيث لا "يتسرب" اتجاهه إلى ما حوله.
//
// هذه الدالة نقية (بلا اعتماد على المحرر) لتُختبر آليًا في test/bidi.test.mjs.

/** @returns {{from:number,to:number,dir:"ltr"|"auto"}[]} */
export function isolatedRanges(line, offset = 0) {
  const out = [];
  const re = /("(?:[^"\\\n]|\\.)*"?|«[^»\n]*»?)|(#.*$)|([A-Za-z_][A-Za-z0-9_]*)|([0-9]+(?:[.][0-9]+)?)/gmu;
  let m;
  while ((m = re.exec(line))) {
    const from = offset + m.index, to = from + m[0].length;
    if (m[1]) {
      // النص الحرفي: اتجاه تلقائي من محتواه، ولا يؤثر في الكود حوله.
      out.push({ from, to, dir: "auto" });
    } else if (m[2]) {
      out.push({ from, to, dir: "auto" });
    } else {
      out.push({ from, to, dir: "ltr" });
    }
  }
  return out;
}

/** هل يحتاج السطر إلى عزل؟ (يحتوي محارف قوية LTR أو أرقامًا غربية أو نصوصًا) */
export function needsIsolation(line) {
  return /[A-Za-z0-9"«#]/.test(line);
}
