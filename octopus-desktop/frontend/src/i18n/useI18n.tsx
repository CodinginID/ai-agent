import { createContext, useCallback, useContext, useMemo, useState } from "react";
import engDict from "./eng.json";
import idDict from "./id.json";

const LANG_KEY = "language";
const SUPPORTED: Array<{ code: string; name: string }> = [
  { code: "en", name: "English" },
  { code: "id", name: "Bahasa Indonesia" },
];

export type LangCode = "en" | "id";
export type Lang = { code: string; name: string };

type I18n = {
  lang: Lang;
  t: (key: string, vars?: Record<string, string>) => string;
  setLang: (code: LangCode) => void;
  supported: readonly Lang[];
};

const DICTS: Record<LangCode, Record<string, string>> = {
  en: engDict as Record<string, string>,
  id: idDict as Record<string, string>,
};

function translate(code: LangCode, key: string, vars?: Record<string, string>): string {
  let msg = DICTS[code][key] ?? DICTS.id[key] ?? key;
  if (vars) {
    msg = msg.replace(/\{\{\s*(\w+)\s*\}\}/g, (_, k) => vars[k] ?? `{{${k}}}`);
  }
  return msg;
}

// Default tanpa provider = bahasa Indonesia (bahasa utama produk), supaya
// komponen tetap terbaca walau provider lupa dipasang.
const I18nCtx = createContext<I18n>({
  lang: SUPPORTED[1],
  t: (key, vars) => translate("id", key, vars),
  setLang: () => {},
  supported: SUPPORTED,
});

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    try {
      const stored = localStorage.getItem(LANG_KEY);
      if (stored === "id" || stored === "en") {
        return SUPPORTED.find((s) => s.code === stored) ?? SUPPORTED[1];
      }
    } catch {
      // localStorage bisa tak tersedia (webview restriktif) — pakai deteksi navigator
    }
    const navLang = typeof navigator !== "undefined" ? navigator.language : "";
    return navLang.startsWith("en") ? SUPPORTED[0] : SUPPORTED[1];
  });

  const setLang = useCallback((code: LangCode) => {
    const target = SUPPORTED.find((s) => s.code === code);
    if (!target) return;
    setLangState(target);
    try {
      localStorage.setItem(LANG_KEY, code);
    } catch {
      // preferensi tetap berlaku untuk sesi ini meski gagal persist
    }
    document.documentElement.lang = code;
  }, []);

  const t = useCallback(
    (key: string, vars?: Record<string, string>) => translate(lang.code as LangCode, key, vars),
    [lang.code],
  );

  const value = useMemo<I18n>(() => ({ lang, t, setLang, supported: SUPPORTED }), [lang, t, setLang]);

  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>;
}

export function useI18n(): I18n {
  return useContext(I18nCtx);
}

export { SUPPORTED };
