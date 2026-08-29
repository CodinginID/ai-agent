import { useEffect, useState } from "react";

// Shell mobile untuk semua layar sentuh "kecil": HP portrait/landscape dan
// tablet portrait (< 1024px), atau layar pendek (HP landscape) — tata letak
// desktop (grid TopBar/aside) baru layak di ≥ 1024px dengan tinggi cukup.
const QUERY = "(max-width: 1023px), (max-height: 520px)";
export const SHORT_QUERY = "(max-height: 520px) and (orientation: landscape)";

function useMedia(query: string): boolean {
  const [on, setOn] = useState<boolean>(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
    return window.matchMedia(query).matches;
  });
  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mql = window.matchMedia(query);
    const onChange = (): void => setOn(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);
  return on;
}

/** Layar pendek landscape (HP dimiringkan): tab bar jadi rail kiri, command bar
 *  dipindah ke sheet supaya kanvas dapat tinggi maksimal. */
export function useShortViewport(): boolean {
  return useMedia(SHORT_QUERY);
}

function matches(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false;
  }
  return window.matchMedia(QUERY).matches;
}

/** SSR-safe: mengembalikan false di render pertama server, lalu sinkron ke
 *  lebar viewport nyata via matchMedia begitu mount di klien. */
export function useIsMobile(): boolean {
  const [mobile, setMobile] = useState<boolean>(matches);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia(QUERY);
    const onChange = (): void => setMobile(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);

  return mobile;
}
