// IndexedDB kecil buat share token akses ke service worker.
// Service worker (sw.ts) tidak bisa baca localStorage — satu-satunya storage
// sinkron yang bisa diakses dari kedua konteks (halaman + SW) adalah IndexedDB.
// DB "octopus", object store "kv" — dipakai sebagai key/value sederhana.

const DB_NAME = "octopus";
const STORE_NAME = "kv";
const DB_VERSION = 1;

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/** Simpan satu value di store "kv" (dipanggil dari halaman, mis. token). */
export async function idbPut(key: string, value: string): Promise<void> {
  const db = await openDb();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readwrite");
    tx.objectStore(STORE_NAME).put(value, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
  db.close();
}

/** Ambil satu value dari store "kv" (dipanggil dari service worker). */
export async function idbGet(key: string): Promise<string | undefined> {
  const db = await openDb();
  const value = await new Promise<string | undefined>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, "readonly");
    const req = tx.objectStore(STORE_NAME).get(key);
    req.onsuccess = () => resolve(req.result as string | undefined);
    req.onerror = () => reject(req.error);
  });
  db.close();
  return value;
}
