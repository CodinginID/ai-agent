# AI Agent — Telegram Server Admin Bot

[![Release](https://img.shields.io/github/v/release/CodinginID/ai-agent)](https://github.com/CodinginID/ai-agent/releases)
[![Docker Image](https://img.shields.io/badge/ghcr.io-ai--agent-blue)](https://github.com/CodinginID/ai-agent/pkgs/container/ai-agent)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Bot Telegram untuk memantau dan mengontrol server menggunakan bahasa natural (Bahasa Indonesia maupun Inggris). Mode chat default didukung oleh **Qwen** via **Ollama** yang berjalan lokal. Integrasi opsional seperti **Codex CLI** dan **Claude Code CLI** dapat mengirim prompt/output ke provider masing-masing saat diaktifkan.

---

## Install dalam 1 Menit

> Butuh: **Docker** yang sudah berjalan di mesin/VPS kamu.

```bash
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/install.sh | bash
```

Script otomatis: download image, tanya token Telegram, jalankan bot. Selesai.

### Atau manual dengan Docker Compose

```bash
# Download konfigurasi
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/docker-compose.yml -o docker-compose.yml
curl -fsSL https://raw.githubusercontent.com/CodinginID/ai-agent/main/.env.example -o .env

# Isi token Telegram
nano .env

# Jalankan
docker compose up -d
```

### Update ke versi terbaru

```bash
docker compose pull && docker compose up -d
```

---

## Fitur

| Kategori | Kemampuan |
|---|---|
| **Server** | Status, uptime, CPU, load average |
| **Memory** | RAM & swap usage |
| **Disk** | Penggunaan per partisi |
| **Proses** | Top 15 proses berdasarkan CPU/RAM |
| **Docker** | Container aktif, images, resource stats |
| **Git** | Status repository |
| **Files** | List file di working directory |
| **Manual** | Jalankan command langsung via `/cmd` |
| **Agent CLI** | Jalankan `/codex`, `/claude`, dan cek status lewat `/agents` |

Semua perintah bisa dikirim dalam bahasa natural, misalnya:
> *"cek ram sekarang"*, *"docker yang jalan apa aja"*, *"status server gimana"*

---

## Kebutuhan Sistem

| Kebutuhan | Keterangan |
|---|---|
| Python | 3.10 atau lebih baru |
| RAM | Minimal 4 GB (untuk model Qwen 3b) |
| Disk | ~3 GB untuk model AI |
| OS | macOS atau Linux (Ubuntu/Debian/RedHat) |
| Ollama | Diinstall otomatis oleh setup script |

---

## Instalasi Cepat

Clone repo lalu jalankan satu perintah:

```bash
git clone <url-repo>
cd ai-agent
bash setup.sh
```

Script akan otomatis:
1. Mengecek versi Python
2. Membuat virtual environment
3. Menginstall semua dependency Python
4. Menginstall Ollama (jika belum ada)
5. Menjalankan Ollama service
6. Mendownload model **Qwen2.5:3b** (~2 GB)
7. Membuat file `.env` dan meminta token Telegram
8. Mengupdate `bot.py` agar membaca konfigurasi dari `.env`

---

## Instalasi Manual

Jika ingin install langkah demi langkah tanpa script:

**1. Buat virtual environment**
```bash
python3 -m venv env
source env/bin/activate
```

**2. Install dependency Python**
```bash
pip install -r requirements.txt
```

**3. Install Ollama**

macOS:
```bash
brew install ollama
```

Linux:
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**4. Jalankan Ollama & download model**
```bash
ollama serve &
ollama pull qwen2.5:3b
```

**5. Buat file `.env`**
```bash
cp .env.example .env
nano .env  # isi token Telegram
```

---

## Konfigurasi

Salin `.env.example` menjadi `.env` lalu sesuaikan nilainya:

```bash
cp .env.example .env
```

| Variable | Wajib | Default | Keterangan |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Ya | — | Token dari [@BotFather](https://t.me/BotFather) |
| `OLLAMA_HOST` | Tidak | `http://localhost:11434` | URL Ollama service |
| `OLLAMA_MODEL` | Tidak | `qwen2.5:3b` | Nama model Ollama |
| `ADMIN_USER_IDS` | Disarankan | _(kosong)_ | User ID Telegram yang boleh akses |
| `ALLOW_UNRESTRICTED_ACCESS` | Tidak | `false` | Development only: izinkan semua user |
| `PROJECT_DIR` | Tidak | `.` (direktori saat ini) | Working directory untuk command |
| `COMMAND_TIMEOUT` | Tidak | `20` | Batas waktu eksekusi command (detik) |
| `ENABLE_CODEX` | Tidak | `false` | Aktifkan `/codex` |
| `ENABLE_CLAUDE` | Tidak | `false` | Aktifkan `/claude` |
| `AGENT_WORKDIR` | Tidak | `.` | Working directory untuk Codex/Claude |
| `AGENT_TIMEOUT` | Tidak | `180` | Timeout Codex/Claude dalam detik |
| `CODEX_SANDBOX` | Tidak | `read-only` | Sandbox Codex: `read-only`, `workspace-write`, atau `danger-full-access` |
| `CLAUDE_ALLOWED_TOOLS` | Tidak | `Read,Grep,Glob` | Tools Claude yang diizinkan |

### Mendapatkan Token Telegram

1. Buka Telegram, cari **@BotFather**
2. Ketik `/newbot` dan ikuti instruksinya
3. Copy token yang diberikan ke `TELEGRAM_BOT_TOKEN` di `.env`

### Membatasi Akses (Opsional)

Isi `ADMIN_USER_IDS` dengan Telegram user ID yang boleh menggunakan bot.
Kirim `/whoami` ke bot untuk mengetahui user ID kamu.

```env
# Satu user
ADMIN_USER_IDS=123456789

# Beberapa user
ADMIN_USER_IDS=123456789,987654321
```

Jika `ADMIN_USER_IDS` dikosongkan, command bot akan ditolak kecuali `/whoami`. Untuk development sementara, set `ALLOW_UNRESTRICTED_ACCESS=true`.

---

## Menjalankan Bot (Lokal / Development)

```bash
source env/bin/activate
python app/bot.py
```

Pastikan Ollama sudah berjalan sebelum menjalankan bot:
```bash
ollama serve &   # atau lewat systemctl di Linux
```

---

## CI/CD dengan GitHub Actions

Setiap kali push ke branch `main`, GitHub Actions otomatis deploy ke VPS — tanpa perlu SSH manual.

```
Push ke main
    │
    ▼
GitHub Actions
  ├── [validate] cek syntax Python + docker-compose
  └── [deploy]   self-hosted runner di VPS → git pull → make up
```

### Kenapa Self-hosted Runner, Bukan SSH Biasa?

VPS yang menggunakan **Cloudflare Access** atau firewall ketat tidak bisa di-SSH langsung dari GitHub Actions. Solusinya: install GitHub Actions runner **di dalam VPS**. Runner menghubungi GitHub secara outbound (bukan inbound), sehingga Cloudflare Access tidak menghalangi.

```
❌ SSH biasa (tidak bisa menembus Cloudflare Access):
   GitHub Actions → SSH → Cloudflare → VPS

✅ Self-hosted runner:
   GitHub Actions ←→ Runner (sudah di dalam VPS)
```

### Setup Satu Kali

**1. SSH masuk ke VPS**
```bash
# Pastikan cloudflared sudah login terlebih dahulu
cloudflared access login ssh-ali.corevice-vps.com
ssh codens-vps
```

**2. Buka halaman runner di GitHub**

`github.com/<username>/<repo>` → **Settings → Actions → Runners → New self-hosted runner**

Pilih **Linux x64**. Halaman tersebut menampilkan perintah install dengan token unik — jalankan di VPS:

```bash
mkdir -p ~/actions-runner && cd ~/actions-runner

# Copy-paste perintah download dari halaman GitHub
curl -o actions-runner-linux-x64.tar.gz -L <URL_DARI_GITHUB>
tar xzf actions-runner-linux-x64.tar.gz

# Konfigurasi dengan token dari halaman GitHub
./config.sh --url https://github.com/<username>/<repo> --token <TOKEN_DARI_GITHUB>
# Nama runner: vps-ali
# Labels: Enter (pakai default)
```

**3. Jalankan runner sebagai systemd service (auto-start saat reboot)**
```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status   # harus: active (running)
```

**4. Clone project dan setup awal di VPS**
```bash
cd ~
git clone https://github.com/<username>/<repo>.git ai-agent
cd ai-agent
cp .env.example .env
nano .env   # isi TELEGRAM_BOT_TOKEN dan ADMIN_USER_IDS
make up     # download model AI (~2GB) + jalankan semua service
```

Workflow deploy default mencari project di `/home/ali/project/codinginid/ai-agent`. Jika ingin path lain, set repository variable `DEPLOY_DIR` dan sesuaikan workflow.

**5. Selesai — tidak ada GitHub Secrets yang perlu ditambahkan untuk deploy.**

Runner sudah berjalan di dalam VPS dengan akses langsung ke Docker dan project.

### Jika Deploy Kuning dan Menunggu Runner

Jika log GitHub Actions berhenti di:

```text
Requested labels: self-hosted, linux
Waiting for a runner to pick up this job...
```

artinya job deploy sudah valid, tetapi GitHub belum menemukan self-hosted runner yang online dan cocok. Cek di VPS:

```bash
cd ~/actions-runner
sudo ./svc.sh status
sudo ./svc.sh start
```

Jika service belum pernah dipasang:

```bash
cd ~/actions-runner
sudo ./svc.sh install
sudo ./svc.sh start
```

Untuk test cepat tanpa systemd:

```bash
cd ~/actions-runner
./run.sh
```

Di GitHub, buka **Settings → Actions → Runners** dan pastikan runner statusnya **Idle** atau **Online** untuk repository ini. Jika runner online tapi label tidak cocok, gunakan label default `self-hosted` saja, atau tambahkan label custom seperti `vps-ali` dan sesuaikan `runs-on` di `.github/workflows/deploy.yml`.

### Jika Deploy Gagal `Permission denied (publickey)`

Error:

```text
git@github.com: Permission denied (publickey).
fatal: Could not read from remote repository.
```

berarti clone lokal di VPS memakai remote SSH, tetapi user runner tidak punya SSH key GitHub yang cocok. Untuk setup multi-akun Git, remote boleh tetap memakai alias, misalnya:

```bash
cd /home/ali/project/codinginid/ai-agent
git remote -v
# origin git@github-work:CodinginID/ai-agent.git
```

Pastikan alias `github-work` ada di `/home/ali/.ssh/config` dan bisa dipakai oleh user runner:

```sshconfig
Host github-work
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_work
  IdentitiesOnly yes
```

Tes dari VPS:

```bash
whoami
ssh -T git@github-work
git -C /home/ali/project/codinginid/ai-agent fetch origin main
```

Jika runner service berjalan sebagai user lain, pindahkan SSH config/key ke user itu atau install ulang service runner sebagai user `ali`. Jika ingin override remote tanpa mengubah repo lokal, set repository variable `DEPLOY_GIT_REMOTE_URL`.

### Cara Kerja Setelah Setup

```bash
# Di komputer lokal
git add .
git commit -m "feat: tambah fitur baru"
git push origin main
# ↑ ini yang memicu deploy otomatis
```

Alur yang terjadi:
```
push ke main
    │
    ├── [validate]  berjalan di GitHub server — cek syntax & docker-compose
    └── [deploy]    berjalan di VPS runner:
                    git pull origin main
                    make up
                    make status
```

Pantau progress di tab **Actions** GitHub repo.

### Trigger Manual

Bisa deploy tanpa push kode: buka GitHub repo → **Actions → Deploy to VPS → Run workflow**.

---

## Deployment ke VPS (Docker)

Cara yang disarankan untuk production. Bot akan otomatis restart jika crash atau VPS reboot, tanpa perlu intervensi manual.

### Kebutuhan

- Docker Engine 24+
- Docker Compose plugin (`docker compose`, bukan `docker-compose`)

Install Docker di VPS (Ubuntu):
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # agar tidak perlu sudo
newgrp docker
```

### Setup Pertama Kali

```bash
# 1. Clone repo di VPS
git clone <url-repo>
cd ai-agent

# 2. Buat file konfigurasi
cp .env.example .env
nano .env   # isi TELEGRAM_BOT_TOKEN dan ADMIN_USER_IDS

# 3. Jalankan semua service
#    (build bot, start Ollama, download model ~2GB, start bot)
make up
```

Proses `make up` pertama kali memerlukan waktu beberapa menit karena mendownload model AI. Pantau progressnya:
```bash
make logs
```

### Perintah Harian

| Perintah | Fungsi |
|---|---|
| `make up` | Jalankan semua service (build ulang jika ada update kode) |
| `make down` | Hentikan semua service |
| `make restart` | Restart hanya bot (Ollama tetap jalan) |
| `make logs` | Ikuti log bot secara realtime |
| `make status` | Lihat status semua container |
| `make shell` | Masuk ke dalam container bot |
| `make pull-model` | Download/update model AI |
| `make clean` | Hapus semua container + volume |

### Update Kode Bot

```bash
git pull
make up   # otomatis build ulang image bot
```

### Ganti Model AI

Edit `.env`:
```env
OLLAMA_MODEL=qwen2.5:7b
```

Lalu download model baru dan restart:
```bash
make pull-model
make restart
```

### Arsitektur Docker

```
┌─────────────────────────────────┐
│         docker-compose          │
│                                 │
│  ┌──────────┐   ┌────────────┐  │
│  │  ollama  │◄──│    bot     │  │
│  │ :11434   │   │  (python)  │  │
│  └──────────┘   └────────────┘  │
│       │                         │
│  [ollama_data volume]           │
│  (model AI tersimpan permanen)  │
└─────────────────────────────────┘
```

- **ollama**: AI model server, auto-restart, data model disimpan di Docker volume
- **ollama-init**: container sekali jalan untuk download model saat pertama deploy
- **bot**: Telegram bot, auto-restart jika crash atau VPS reboot

### Auto-restart saat VPS Reboot

Sudah otomatis karena semua service menggunakan `restart: unless-stopped`. Selama Docker daemon berjalan saat startup (default di Ubuntu), bot akan hidup kembali sendiri setelah reboot.

Verifikasi:
```bash
sudo systemctl is-enabled docker   # harus: enabled
```

---

## Cara Pakai

### Perintah Slash

| Command | Fungsi |
|---|---|
| `/start` atau `/help` | Tampilkan panduan singkat |
| `/whoami` | Tampilkan Telegram user ID kamu |
| `/cmd <perintah>` | Jalankan command manual langsung |

### Pesan Bebas (Bahasa Natural)

Ketik saja instruksi biasa, bot akan memahami maksudnya:

```
cek status server
cek ram
cek disk
docker yang jalan apa aja
docker image ada apa
git status
list file
proses apa yang paling banyak makan cpu
```

### Manual Command via `/cmd`

Untuk command yang lebih spesifik, gunakan `/cmd` diikuti perintahnya:

```
/cmd docker ps -a
/cmd git log --oneline -5
/cmd df -h
/cmd ls -lah /var/log
```

Command yang diizinkan: `docker`, `git`, `ls`, `ps`, `df`, `du`, `free`, `uptime`, `whoami`, `pwd`, `hostname`

---

## Pilihan Model AI

Model default adalah `qwen2.5:3b` yang ringan. Bisa diganti sesuai kebutuhan:

| Model | RAM | Kecerdasan | Cocok untuk |
|---|---|---|---|
| `qwen2.5:3b` | ~3 GB | Cukup | VPS / server kecil |
| `qwen2.5:7b` | ~5 GB | Lebih baik | Server dengan RAM ≥ 8 GB |
| `qwen2.5:14b` | ~9 GB | Terbaik | Server dengan RAM ≥ 16 GB |

Ganti model di file `.env`:
```env
OLLAMA_MODEL=qwen2.5:7b
```

Lalu download modelnya:
```bash
ollama pull qwen2.5:7b
```

---

## Struktur Proyek

```
ai-agent/
├── .github/
│   └── workflows/
│       └── deploy.yml    # CI/CD: auto-deploy ke VPS saat push ke main
├── app/
│   └── bot.py            # Kode utama bot
├── .env                  # Konfigurasi lokal (tidak di-commit)
├── .env.example          # Template konfigurasi
├── Dockerfile            # Image untuk container bot
├── docker-compose.yml    # Orchestrasi bot + Ollama
├── Makefile              # Shortcut perintah Docker
├── requirements.txt      # Dependency Python
└── setup.sh              # Script instalasi untuk development lokal
```

---

## Troubleshooting

**Bot tidak merespons**
- Pastikan token di `.env` sudah benar
- Cek apakah bot sudah di-start dengan `/start`

**Ollama tidak bisa dihubungi**
```bash
curl http://localhost:11434   # harus ada respons
ollama serve                  # jalankan jika belum
```

**Model belum terdownload**
```bash
ollama list                   # cek model yang ada
ollama pull qwen2.5:3b        # download model
```

**Cek Telegram user ID**

Kirim `/whoami` ke bot untuk melihat user ID kamu, lalu tambahkan ke `ADMIN_USER_IDS` di `.env`.

**Bot tidak jalan setelah `make up`**
```bash
make logs              # lihat error message
make status            # cek status tiap container
```

**`dependency failed to start: container aiagent_ollama is unhealthy`**

Artinya Compose menunggu service `ollama` menjadi healthy, tetapi healthcheck gagal sebelum timeout. Cek detailnya:

```bash
make status
make logs-ollama
docker inspect aiagent_ollama --format '{{json .State.Health}}'
```

Jika log menunjukkan Ollama sebenarnya sudah berjalan, coba restart stack:

```bash
docker compose down
docker compose up -d --build
```

Jika VPS kecil atau cold start lambat, tunggu 1-2 menit lalu cek:

```bash
docker compose exec ollama ollama list
make logs-init
```

**Ollama belum selesai siap saat bot start**

Bot menunggu Ollama healthy sebelum start. Jika timeout, jalankan ulang:
```bash
make restart
```

**Model AI belum ada saat pertama deploy**
```bash
docker compose logs ollama-init   # cek progress download model
```

**Melihat log Ollama**
```bash
docker compose logs -f ollama
```
