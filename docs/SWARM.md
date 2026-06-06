# Swarm Deployment — Octopus (Tahap 1: scalable)

Panduan menjalankan octopus di **Docker Swarm** supaya backend bisa di-replicate
saat user banyak. File stack: [`../docker-stack.yml`](../docker-stack.yml).

> **Status:** stack file sudah ditulis & divalidasi (`docker stack config` ✓), dan
> mekanik scaling swarm sudah diuji di node ini (scale 1→3 converged). Stack
> **belum di-deploy** — octopus saat ini masih jalan via `docker compose` di port
> 8090. Bagian "Cutover" di bawah adalah langkah go-live saat Anda siap.

---

## Kenapa Swarm (bukan langsung Kubernetes)

- Swarm **sudah aktif** di VPS ini (1 node, leader) — nol biaya setup.
- Sintaks = compose + blok `deploy:` → tidak perlu belajar manifest baru.
- Memberi 80% manfaat (replikasi, rolling update, self-heal) dengan 20% kerumitan.
- K8s + autoscaling (HPA) baru worth-it saat **multi-node** (Tahap 2/3).

## Peta scaling tiap service

| Service | Replicas | Kenapa |
|---|---|---|
| **bot** | **2 (scalable)** | Stateless dispatcher. Kode multi-instance ready (Redis pub/sub B5g). **Ini yang di-scale saat user banyak.** |
| redis | 1 (pinned) | State bersama (sesi, rate-limit, presence). HA sejati = Sentinel/cluster (nanti). |
| ollama | 1 (pinned) | **Bottleneck asli** (CPU/RAM, 4GB). Scale = pindah ke node/GPU sendiri (Tahap 3). |
| caddy | 1 | Ingress; routing mesh swarm auto load-balance ke semua replica bot. |
| telegram-adapter | **1 (wajib)** | Telegram `getUpdates` single-consumer; >1 = error 409. |

---

## Prasyarat sekali jalan: build & push image

Swarm **tidak bisa `build:`** — hanya jalankan image jadi. Build & push dulu:

```bash
cd ~/ai-agent
# bot (sudah ada di ghcr biasanya via CI, tapi kalau mau dari source):
docker build -t ghcr.io/codinginid/ai-agent:latest .
docker push ghcr.io/codinginid/ai-agent:latest

# telegram-adapter (di compose pakai build: ./telegram-adapter):
docker build -t ghcr.io/codinginid/ai-agent-telegram:latest ./telegram-adapter
docker push ghcr.io/codinginid/ai-agent-telegram:latest
```

> `.env` & `Caddyfile` dibaca dari direktori saat `docker stack deploy` dijalankan.
> Pastikan Anda di `~/ai-agent` saat deploy.

---

## Deploy

```bash
cd ~/ai-agent
docker stack deploy -c docker-stack.yml octopus

# pantau sampai semua replica Running:
watch docker stack services octopus
```

## Scale (jawaban "auto-replicate saat user banyak")

```bash
# manual scale backend ke 4 replica:
docker service scale octopus_bot=4

# swarm sebar otomatis + routing mesh load-balance. Verifikasi:
docker service ps octopus_bot
```

> **Auto-scale berdasarkan beban** (naik-turun sendiri) BUKAN fitur bawaan Swarm —
> itu butuh Tahap 2 (k3s + HorizontalPodAutoscaler). Di Swarm, scaling-nya manual
> (atau via skrip cron yang baca metrik lalu `service scale`).

## Rolling update (deploy versi baru, zero-downtime)

Stack sudah di-set `order: start-first` + `failure_action: rollback`:

```bash
docker service update --image ghcr.io/codinginid/ai-agent:NEWTAG octopus_bot
# replica baru start & lolos health DULU, baru yang lama dimatikan.
# kalau health gagal dalam 30s → otomatis rollback ke versi lama.
```

## Rollback manual

```bash
docker service rollback octopus_bot
```

## Status & log

```bash
docker stack services octopus              # ringkasan replica per service
docker service ps   octopus_bot            # task tiap replica + state
docker service logs -f octopus_bot         # log gabungan semua replica
```

---

## Cutover dari compose → swarm (go-live, saat siap)

Octopus live sekarang pakai `docker compose` (container `aiagent_*`) di port 8090.
Stack swarm juga mau publish 8090 → **akan bentrok**. Urutan aman:

```bash
cd ~/ai-agent
# 1. matikan stack compose (volume redis/ollama/caddy TETAP aman, named volume):
docker compose down                 # JANGAN pakai -v (itu hapus volume!)

# 2. deploy swarm (pakai volume yang sama: aiagent_ollama_data, dst):
docker stack deploy -c docker-stack.yml octopus

# 3. verifikasi dari luar (tunnel cloudflared → 127.0.0.1:8090 tetap sama):
curl -fsS http://127.0.0.1:8090/health
```

Rollback cutover (balik ke compose):

```bash
docker stack rm octopus
sleep 5
docker compose up -d
```

> Volume bersifat **named & eksternal-aman** (`aiagent_*`), jadi data Redis &
> model Ollama tidak hilang saat pindah compose↔swarm.

---

## Batas di 1 VPS (jujur)

Scaling `bot` hanya membantu sampai CPU/RAM VPS penuh, DAN selama beban AI tidak
naik (karena Ollama tetap 1). Skalabilitas sejati = **tambah node** ke swarm
(`docker swarm join`) lalu service otomatis tersebar. Saat itu tiba, pertimbangkan
Tahap 2 (k3s + HPA) untuk auto-scale berbasis metrik.
