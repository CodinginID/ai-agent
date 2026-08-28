/// <reference lib="webworker" />
// Service worker — precache (Workbox injectManifest) + Web Push + notification actions.
//
// Push payload (dari app/ports/push.py PushMessage, lihat app/adapters/push_webpush.py):
//   { title, body, tag, url, kind, data }
// kind === "approval" → tombol "Setujui"/"Tolak" yang panggil /chat/approve|/chat/reject
// langsung dari notifikasi (worker tidak perlu tab aplikasi terbuka).

import { cleanupOutdatedCaches, precacheAndRoute } from "workbox-precaching";
import { idbGet } from "./net/idb";

declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<{ url: string; revision: string | null }>;
};

precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

// Mode "prompt" (vite.config.ts): SW baru menunggu sampai user tekan "Perbarui"
// di UpdateButton → updateServiceWorker() kirim SKIP_WAITING ke SW ini.
self.addEventListener("message", (event) => {
  if ((event.data as { type?: string } | null)?.type === "SKIP_WAITING") {
    void self.skipWaiting();
  }
});
self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

interface PushPayload {
  title: string;
  body: string;
  tag: string;
  url: string;
  kind: string;
  data: Record<string, string>;
}

// TS's lib.dom/lib.webworker NotificationOptions belum punya `actions` (fitur
// Notification Actions API — didukung browser, cuma belum di-type oleh TS).
interface NotificationOptionsWithActions extends NotificationOptions {
  actions?: Array<{ action: string; title: string; icon?: string }>;
}

function parsePushPayload(event: PushEvent): PushPayload | null {
  if (!event.data) return null;
  try {
    return event.data.json() as PushPayload;
  } catch {
    return null;
  }
}

self.addEventListener("push", (event: PushEvent) => {
  const payload = parsePushPayload(event);
  if (!payload) return;

  const actions =
    payload.kind === "approval"
      ? [
          { action: "approve", title: "Setujui" },
          { action: "reject", title: "Tolak" },
        ]
      : [];

  const options: NotificationOptionsWithActions = {
    body: payload.body,
    tag: payload.tag,
    data: { url: payload.url, kind: payload.kind, ...payload.data },
    icon: "/pwa-192.png",
    badge: "/pwa-192.png",
    actions,
  };

  event.waitUntil(self.registration.showNotification(payload.title, options));
});

async function decidePlan(path: string, planId: string): Promise<boolean> {
  const token = await idbGet("token");
  if (!token) return false;
  try {
    const resp = await fetch(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ plan_id: planId, as_email: "demo@local" }),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

async function focusOrOpen(url: string): Promise<void> {
  const clientsList = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
  for (const client of clientsList) {
    if ("focus" in client) {
      await client.focus();
      return;
    }
  }
  await self.clients.openWindow(url);
}

self.addEventListener("notificationclick", (event: NotificationEvent) => {
  const notif = event.notification;
  const data = (notif.data ?? {}) as { url?: string; plan_id?: string };
  notif.close();

  if (event.action === "approve" || event.action === "reject") {
    const planId = data.plan_id ?? "";
    const path = event.action === "approve" ? "/chat/approve" : "/chat/reject";
    event.waitUntil(
      decidePlan(path, planId).then((ok) =>
        self.registration.showNotification(
          ok ? (event.action === "approve" ? "Disetujui" : "Ditolak") : "Gagal",
          { tag: notif.tag, body: ok ? "" : "Aksi gagal, coba lagi dari aplikasi." },
        ),
      ),
    );
    return;
  }

  event.waitUntil(focusOrOpen(data.url ?? "/"));
});

// Browser rotasi push subscription (mis. kadaluwarsa) — re-subscribe pakai
// applicationServerKey lama lalu daftar ulang ke backend.
self.addEventListener("pushsubscriptionchange", (event: PushSubscriptionChangeEvent) => {
  const oldSub = event.oldSubscription;
  if (!oldSub) return;
  const key = oldSub.options.applicationServerKey;

  event.waitUntil(
    (async () => {
      const newSub = await self.registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: key,
      });
      const token = await idbGet("token");
      if (!token) return;
      await fetch("/push/subscribe", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ ...newSub.toJSON(), as_email: "demo@local" }),
      });
    })(),
  );
});
