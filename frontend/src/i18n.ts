// Interface language (NFR-04: Arabic first, with English).
//
// The components are written in Arabic. In English mode a small translator swaps
// rendered Arabic text and attributes for their English entries in EN, and keeps
// doing so as React updates the page. Unknown text stays Arabic rather than breaking.
import { EN, EN_PATTERNS } from "./locales/en";

export type Lang = "ar" | "en";
const KEY = "mihakk.lang";
const ARABIC = /[؀-ۿ]/;
const ATTRIBUTES = ["placeholder", "title", "aria-label", "alt"];

export function getLang(): Lang {
  try {
    return localStorage.getItem(KEY) === "en" ? "en" : "ar";
  } catch {
    return "ar";
  }
}

export function setLang(lang: Lang): void {
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    /* private mode: the choice lasts for this page only */
  }
  window.location.reload();
}

export function translate(text: string): string {
  if (!ARABIC.test(text)) return text;
  const trimmed = text.trim();
  const exact = EN[trimmed];
  if (exact !== undefined) return text.replace(trimmed, exact);
  for (const [pattern, english] of EN_PATTERNS) {
    if (pattern.test(trimmed)) return text.replace(trimmed, trimmed.replace(pattern, english));
  }
  return text;
}

function translateNode(node: Node): void {
  if (node.nodeType === Node.TEXT_NODE) {
    const value = node.nodeValue ?? "";
    const next = translate(value);
    if (next !== value) node.nodeValue = next;
    return;
  }
  if (!(node instanceof Element)) return;
  for (const name of ATTRIBUTES) {
    const value = node.getAttribute(name);
    if (value && ARABIC.test(value)) {
      const next = translate(value);
      if (next !== value) node.setAttribute(name, next);
    }
  }
  if (node.tagName === "SCRIPT" || node.tagName === "STYLE" || node.tagName === "TEXTAREA") return;
  node.childNodes.forEach(translateNode);
}

export function startTranslator(): void {
  const lang = getLang();
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "en" ? "ltr" : "rtl";
  if (lang !== "en") return;
  document.title = translate(document.title);
  const original = { confirm: window.confirm.bind(window), alert: window.alert.bind(window) };
  window.confirm = (message?: string) => original.confirm(translate(String(message ?? "")));
  window.alert = (message?: string) => original.alert(translate(String(message ?? "")));
  translateNode(document.body);
  new MutationObserver((mutations) => {
    for (const m of mutations) {
      if (m.type === "characterData") translateNode(m.target);
      else if (m.type === "attributes") translateNode(m.target);
      else m.addedNodes.forEach(translateNode);
    }
  }).observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: ATTRIBUTES,
  });
}
