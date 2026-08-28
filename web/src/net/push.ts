// Web Push (klien) — subscribe/unsubscribe browser + badge ikon aplikasi.
// Service worker (sw.ts) yang menampilkan notifikasi & menangani tombol aksi;
// modul ini cuma ngurus lifecycle subscription + sinkronisasi token ke SW.

import { API_BASE, getToken } from "./api";
import { idbPut } from "./idb";

export type PushState = "unsupported" | "denied" | "enabled" | "disabled";

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/** Konversi VAPID public key (base64url) → Uint8Array buat applicationServerKey. */
function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

export async function getPushState(): Promise<PushState> {
  if (!isPushSupported()) return "unsupported";
  if (Notification.permission === "denied") return "denied";
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    return sub ? "enabled" : "disabled";
  } catch {
    return "disabled";
  }
}

async function fetchVapidPublicKey(): Promise<string | null> {
  try {
    const resp = await fetch(`${API_BASE}/push/vapid-public-key`, {
      headers: authHeaders(),
    });
    if (!resp.ok) return null;
    const body = (await resp.json()) as { key?: string };
    return body.key ?? null;
  } catch {
    return null;
  }
}

async function postSubscription(sub: PushSubscription): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/push/subscribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ ...sub.toJSON(), as_email: "demo@local" }),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

/** Minta izin notifikasi + subscribe push manager + daftarkan ke backend. */
export async function enablePush(): Promise<boolean> {
  if (!isPushSupported()) return false;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return false;

  const key = await fetchVapidPublicKey();
  if (!key) return false;

  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      // TS 5.9's TypedArray<ArrayBufferLike> vs BufferSource<ArrayBuffer> split
      // rejects this structurally even though it's valid at runtime.
      applicationServerKey: urlBase64ToUint8Array(key) as BufferSource,
    });
    return await postSubscription(sub);
  } catch {
    return false;
  }
}

/** Batalkan subscription lokal + beri tahu backend supaya berhenti kirim. */
export async function disablePush(): Promise<boolean> {
  if (!isPushSupported()) return false;
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (!sub) return true;
    const endpoint = sub.endpoint;
    await sub.unsubscribe();
    await fetch(`${API_BASE}/push/unsubscribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ endpoint, as_email: "demo@local" }),
    });
    return true;
  } catch {
    return false;
  }
}

/** Salin token akses saat ini ke IndexedDB supaya service worker bisa
 *  panggil /chat/approve|/chat/reject saat tombol notifikasi ditekan. */
export async function syncTokenToSw(): Promise<void> {
  const token = getToken();
  if (!token) return;
  try {
    await idbPut("token", token);
  } catch {
    /* IndexedDB tidak tersedia (mis. private mode ketat) — abaikan */
  }
}

/** App badge (ikon aplikasi di homescreen/taskbar) — jumlah approval pending. */
export function setBadge(n: number): void {
  try {
    if (!("setAppBadge" in navigator)) return;
    if (n > 0) {
      void (navigator as unknown as { setAppBadge: (n: number) => Promise<void> })
        .setAppBadge(n)
        .catch(() => {});
    } else if ("clearAppBadge" in navigator) {
      void (navigator as unknown as { clearAppBadge: () => Promise<void> })
        .clearAppBadge()
        .catch(() => {});
    }
  } catch {
    /* API tidak didukung browser ini — abaikan */
  }
}
