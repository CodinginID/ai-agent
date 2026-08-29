// Riwayat rilis web Ruang Octopus — entri TERATAS = versi yang sedang di-build.
// Dibaca vite.config.ts saat build → dist/version.json (dipakai UpdateButton
// untuk menampilkan "apa yang baru" sebelum user memuat ulang versi baru).
// Tambah entri baru di atas setiap PR yang mengubah web/ (bump juga
// package.json "version" supaya sama).

export interface ReleaseNote {
  version: string;
  date: string; // YYYY-MM-DD
  notes: string[];
}

export const CHANGELOG: ReleaseNote[] = [
  {
    version: "0.3.0",
    date: "2026-08-29",
    notes: [
      "Tampilan mobile ala aplikasi: tab bar bawah (Ruangan · Persetujuan · Aktivitas · Pasukan) + command bar bawah bergaya chat.",
      "Sheet persetujuan otomatis muncul saat Manajer minta persetujuan baru sambil kamu di HP.",
      "Menu ⋯ \"Lainnya\" merapikan provider BYOK, versi/update, dan ganti tema di satu tempat.",
      "Kelola pasukan: ganti nama & peran agen, tambah agen baru, atau hapus — langsung dari tab Pasukan (mobile) atau tombol \"Kelola\" di Roster (desktop). Manajer tak bisa dihapus.",
    ],
  },
  {
    version: "0.2.0",
    date: "2026-08-28",
    notes: [
      "Notifikasi push: tombol 🔔 di bar atas — dapat notifikasi saat Manajer minta persetujuan atau tugas selesai, walau aplikasi tertutup.",
      "Setujui / Tolak langsung dari tombol notifikasi tanpa membuka aplikasi.",
      "Badge angka di ikon aplikasi = jumlah persetujuan yang menunggu.",
      "Tombol versi & pembaruan: aplikasi mengecek versi baru otomatis dan menampilkan daftar perubahan sebelum memuat ulang.",
      "Ikon PNG untuk iOS (Add to Home Screen) + mode standalone.",
    ],
  },
  {
    version: "0.1.0",
    date: "2026-08-26",
    notes: [
      "Ruang gather-room live: roster pasukan, kanban, feed aktivitas dari backend.",
      "Kartu persetujuan live (Setujui/Tolak dieksekusi di backend).",
      "Pengaturan provider BYOK dan command bar /use <provider>.",
    ],
  },
];
