import { useEffect, useState } from "react";

// Sinkron dengan breakpoint Tailwind "md" (768px) — App.tsx pakai batas yang
// sama untuk memutuskan MobileShell vs tata letak desktop.
const QUERY = "(max-width: 767px)";

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
