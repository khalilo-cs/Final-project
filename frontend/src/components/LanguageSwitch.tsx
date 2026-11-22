import { getLang, setLang } from "../i18n";

// Shows the other language in its own script, so it is readable whichever is active.
export function LanguageSwitch() {
  const lang = getLang();
  return (
    <button
      type="button"
      onClick={() => setLang(lang === "ar" ? "en" : "ar")}
      className="rounded-lg border border-slate-200 px-2 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-100"
      aria-label={lang === "ar" ? "Switch to English" : "التبديل إلى العربية"}
    >
      <span lang={lang === "ar" ? "en" : "ar"}>{lang === "ar" ? "English" : "العربية"}</span>
    </button>
  );
}
