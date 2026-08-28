// Info versi aplikasi: versi yang sedang berjalan (build-time) + versi terbaru
// di server (/version.json, selalu network, no-store) untuk tampilan "apa yang baru".

import type { ReleaseNote } from "../changelog";

export const CURRENT_VERSION: string = __APP_VERSION__;

export interface VersionInfo {
  version: string;
  builtAt: string;
  notes: string[];
  history: ReleaseNote[];
}

/** Ambil /version.json dari server (bypass cache SW & HTTP). null kalau offline. */
export async function fetchLatestVersion(): Promise<VersionInfo | null> {
  try {
    const resp = await fetch(`/version.json?t=${Date.now()}`, { cache: "no-store" });
    if (!resp.ok) return null;
    const body = (await resp.json()) as Partial<VersionInfo>;
    if (typeof body.version !== "string") return null;
    return {
      version: body.version,
      builtAt: typeof body.builtAt === "string" ? body.builtAt : "",
      notes: Array.isArray(body.notes) ? body.notes.map(String) : [],
      history: Array.isArray(body.history) ? body.history : [],
    };
  } catch {
    return null;
  }
}
