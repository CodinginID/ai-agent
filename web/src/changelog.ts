// Riwayat rilis web Ruang Octopus — entri TERATAS = versi yang sedang di-build.
// Dibaca vite.config.ts saat build → dist/version.json (dipakai Pengaturan →
// Tentang untuk menampilkan "apa yang baru" sebelum user memuat ulang versi
// baru). Tambah entri baru di atas setiap PR yang mengubah web/ (bump juga
// package.json "version" supaya sama).

export interface ReleaseNote {
  version: string;
  date: string; // YYYY-MM-DD
  notes: string[];
}

export const CHANGELOG: ReleaseNote[] = [
  {
    version: "0.5.0",
    date: "2026-08-30",
    notes: [
      "Otak (LLM provider) kini bisa \"claude-cli\"/\"glm-cli\" — Claude Code atau GLM CLI di device kamu sendiri, tanpa API key, dijalankan lewat worker.",
      "Perintah cepat /use <provider> di kolom perintah untuk ganti otak tanpa buka Pengaturan (juga /otak untuk lihat yang aktif, /help untuk daftar perintah).",
      "Otak aktif kini tampil sebagai chip di header — ketuk untuk buka Pengaturan.",
    ],
  },
  {
    version: "0.4.4",
    date: "2026-08-30",
    notes: [
      "Ruangan kembali realtime lewat URL tunnel: event live kini lewat WebSocket (SSE tertahan proxy), persetujuan & pergerakan agen muncul seketika.",
    ],
  },
  {
    version: "0.4.3",
    date: "2026-08-30",
    notes: [
      "Nama/peran pasukan yang sudah disimpan kini selalu tampil (sebelumnya kembali ke default bila stream ruangan tertahan proxy).",
      "Snapshot ruangan diambil via JSON saat mulai, setelah masuk, dan tiap 20 detik sebagai cadangan.",
    ],
  },
  {
    version: "0.4.2",
    date: "2026-08-29",
    notes: [
      "Tampilan Ruangan di HP dirancang ulang mengikuti mockup: 5 zona dalam grid portrait (Meja Manajer, Ruang Review, Area Kerja, Server, Meeting), avatar kotak dengan ikon peran & cincin status, tanpa zoom/pan berlebihan.",
    ],
  },
  {
    version: "0.4.1",
    date: "2026-08-29",
    notes: [
      "Pengaturan → Akun: masuk dengan token akses atau Google (bila server mengaktifkannya), lihat status sesi, keluar.",
      "Bila belum masuk, Pengaturan terbuka otomatis dan ikon ⚙ berbadge kuning — memperbaiki error \"Missing Bearer token\" saat menyimpan pasukan.",
      "Stream ruangan tersambung otomatis setelah masuk tanpa memuat ulang.",
    ],
  },
  {
    version: "0.4.0",
    date: "2026-08-29",
    notes: [
      "Menu Pengaturan baru (ikon ⚙): notifikasi, provider LLM, tema (termasuk mode Sistem), kelola pasukan, dan halaman Tentang.",
      "Halaman Tentang: tombol periksa/perbarui versi dan riwayat perubahan.",
      "Tombol-tombol di header dirapikan menjadi satu ikon ⚙.",
    ],
  },
  {
    version: "0.3.3",
    date: "2026-08-29",
    notes: ["Ikon aplikasi baru (gurita vektor) — tampil benar saat Add to Home Screen di iOS/Android."],
  },
  {
    version: "0.3.2",
    date: "2026-08-29",
    notes: [
      "Perbaikan iPhone: tab bar kini menempel di dasar layar (tidak ada celah kosong di atas home indicator).",
      "Kanvas ruangan di HP tidak lagi terlalu zoom; petunjuk yang menutupi kartu manajer disembunyikan.",
    ],
  },
  {
    version: "0.3.1",
    date: "2026-08-29",
    notes: [
      "Tampilan mobile kini dipakai juga di tablet portrait dan HP landscape (rail tab di kiri, tombol tulis perintah di header).",
      "Teks & tombol lebih besar dan nyaman disentuh; input tidak lagi memicu zoom otomatis di iOS.",
      "Header menghormati area status bar (notch), transisi tab & sheet lebih halus.",
    ],
  },
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
