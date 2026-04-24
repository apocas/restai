// RESTai internationalization setup.
//
// Language resolution order:
//   1. Authenticated user.options.language (applied from JWTAuthContext
//      once whoami resolves — see `applyLanguage` below)
//   2. localStorage `restai_language` (set by the topbar picker and by
//      applyLanguage for pre-login continuity across sessions)
//   3. `navigator.language` via the language-detector
//   4. `en` (fallback + default)
//
// Locale files live at ./locales/<code>/translation.json. Keep the key
// tree scoped by page/area (e.g. `dashboard.cardProjects`) so hunting
// strings during translation is easy.

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

import en from "./locales/en/translation.json";
import ptPT from "./locales/pt-PT/translation.json";
import zhCN from "./locales/zh-CN/translation.json";
import da from "./locales/da/translation.json";
import de from "./locales/de/translation.json";
import es from "./locales/es/translation.json";
import fr from "./locales/fr/translation.json";
import it from "./locales/it/translation.json";
import nl from "./locales/nl/translation.json";

export const SUPPORTED_LANGUAGES = [
  { code: "en",    label: "English",                nativeLabel: "English" },
  { code: "da",    label: "Danish",                 nativeLabel: "Dansk" },
  { code: "de",    label: "German",                 nativeLabel: "Deutsch" },
  { code: "es",    label: "Spanish",                nativeLabel: "Español" },
  { code: "fr",    label: "French",                 nativeLabel: "Français" },
  { code: "it",    label: "Italian",                nativeLabel: "Italiano" },
  { code: "nl",    label: "Dutch",                  nativeLabel: "Nederlands" },
  { code: "pt-PT", label: "Portuguese (Portugal)",  nativeLabel: "Português" },
  { code: "zh-CN", label: "Chinese (Simplified)",   nativeLabel: "中文" },
];

// Resolve the initial language BEFORE init() so i18next builds the
// fallback chain (`languages` array) against a supported code from
// the start. Without this, a browser locale like "en-US" lands in
// `i18n.languages = ["en"]` and later `changeLanguage("pt-PT")` fails
// to rebuild the chain — the translator keeps resolving through "en"
// and returns English strings despite i18n.language having changed.
const SUPPORTED_CODES = SUPPORTED_LANGUAGES.map((l) => l.code);
function pickInitialLanguage() {
  try {
    const fromLs = typeof localStorage !== "undefined" && localStorage.getItem("restai_language");
    if (fromLs && SUPPORTED_CODES.includes(fromLs)) return fromLs;
  } catch {}
  const nav = typeof navigator !== "undefined" && (navigator.language || "");
  if (nav) {
    if (SUPPORTED_CODES.includes(nav)) return nav;
    const base = nav.split("-")[0];
    const match = SUPPORTED_CODES.find((c) => c.split("-")[0] === base);
    if (match) return match;
  }
  return "en";
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      "en":    { translation: en },
      "da":    { translation: da },
      "de":    { translation: de },
      "es":    { translation: es },
      "fr":    { translation: fr },
      "it":    { translation: it },
      "nl":    { translation: nl },
      "pt-PT": { translation: ptPT },
      "zh-CN": { translation: zhCN },
    },
    lng: pickInitialLanguage(),
    fallbackLng: "en",
    supportedLngs: SUPPORTED_CODES,
    // DO NOT enable nonExplicitSupportedLngs — with supportedLngs
    // containing only full region codes (pt-PT, zh-CN), it strips
    // "pt-PT" → "pt" before the supportedLngs check and rejects it,
    // then toResolveHierarchy collapses to just the fallback "en" and
    // every t() returns English no matter what i18n.language says.
    // Base-code browser locales (eg. "pt") are already normalized in
    // pickInitialLanguage() above, so this flag is redundant anyway.
    load: "currentOnly",
    interpolation: { escapeValue: false },  // React already escapes
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "restai_language",
      caches: ["localStorage"],
    },
    react: {
      useSuspense: false,
      bindI18n: "languageChanged loaded",
    },
  });

/**
 * Apply a language choice end-to-end: switch i18next, persist to
 * localStorage so the pre-login screens pick it up too. Call this
 * from (a) the topbar picker onChange and (b) JWTAuthContext after
 * whoami resolves with a user who has `options.language` set.
 */
export function applyLanguage(lang) {
  if (!lang) return;
  try { localStorage.setItem("restai_language", lang); } catch {}
  if (i18n.language !== lang) i18n.changeLanguage(lang);
}

export default i18n;
