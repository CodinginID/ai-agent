# CLAUDE.md — Panduan Pengembangan AI Agent Bot

File ini dibaca otomatis oleh Claude Code setiap sesi. Ikuti semua aturan di sini tanpa perlu diingatkan ulang.

---

## Konteks Proyek

Telegram bot untuk memantau dan mengontrol server via bahasa natural. AI model (Qwen via Ollama) berjalan lokal di VPS — tidak ada data yang keluar ke cloud.

**Stack:** Python 3.13 · python-telegram-bot · Ollama · Docker · GitHub Actions

---

## Arsitektur: Hexagonal (Ports & Adapters)

Proyek ini menggunakan **Hexagonal Architecture**. Tujuannya: business logic tidak bergantung pada framework, library eksternal, atau infrastruktur.

```
┌─────────────────────────────────────────────────────────┐
│                        ADAPTERS                         │
│                                                         │
│  TelegramAdapter   OllamaAdapter   PsutilMonitor        │
│  (messaging)       (ai provider)   (system metrics)     │
│        │                │                │              │
└────────┼────────────────┼────────────────┼──────────────┘
         │                │                │
┌────────▼────────────────▼────────────────▼──────────────┐
│                         PORTS                           │
│                    (abstract interfaces)                 │
│                                                         │
│   MessengerPort    AIProviderPort   SystemMonitorPort   │
└────────────────────────────┬────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────┐
│                        DOMAIN                           │
│              (pure Python, zero dependencies)           │
│                                                         │
│   Intent · ActionResult · IntentClassifier              │
│   ActionRegistry · HandleMessageUseCase                 │
└─────────────────────────────────────────────────────────┘
```

### Target Struktur Direktori

```
app/
├── domain/
│   ├── entities.py        # Intent, ActionResult, dataclass murni
│   ├── exceptions.py      # Domain exceptions
│   └── use_cases.py       # HandleMessageUseCase (orchestrator)
├── ports/
│   ├── ai_provider.py     # Protocol AIProvider
│   ├── messenger.py       # Protocol Messenger
│   └── system_monitor.py  # Protocol SystemMonitor
├── adapters/
│   ├── ollama.py          # OllamaAdapter implements AIProvider
│   ├── telegram.py        # TelegramAdapter implements Messenger
│   └── psutil_monitor.py  # PsutilMonitor implements SystemMonitor
├── actions/
│   ├── base.py            # Action Protocol + ActionRegistry
│   ├── server.py          # ServerStatusAction, MemoryAction, DiskAction
│   ├── docker.py          # DockerPsAction, DockerImagesAction, etc.
│   └── git.py             # GitStatusAction
├── config.py              # Semua env var di satu tempat
└── main.py                # Dependency injection + entrypoint
```

### Aturan Per Layer

**Domain** (`domain/`)
- Zero import dari library eksternal (tidak boleh import `requests`, `telegram`, `psutil`, dll.)
- Hanya boleh import dari Python standard library dan sesama modul domain
- Semua entity menggunakan `dataclass` atau `NamedTuple`
- Tidak ada I/O (tidak ada file read/write, tidak ada network call)

**Ports** (`ports/`)
- Hanya berisi `Protocol` class (dari `typing`)
- Tidak ada implementasi, hanya definisi method signature
- Setiap port merepresentasikan satu dependen eksternal

**Adapters** (`adapters/`)
- Satu adapter per dependen eksternal
- Hanya boleh diimport dari `main.py` (dependency injection)
- Error dari library eksternal wajib di-wrap menjadi domain exception

**Actions** (`actions/`)
- Setiap action adalah class yang implement `Action` Protocol
- Satu file per domain (server, docker, git, dll.)
- Tidak boleh mengandung business logic parsing intent

---

## Standar Kode

### Prinsip Wajib

1. **Single Responsibility** — satu class/function satu tanggung jawab
2. **Dependency Injection** — jangan instantiate dependencies di dalam class, terima lewat constructor
3. **Explicit over Implicit** — type hint di semua function signature tanpa pengecualian
4. **No Magic** — hindari metaprogramming, dynamic attribute, `eval`, `exec`
5. **Fail Fast** — validasi di boundary (config load, adapter init), bukan di tengah business logic

### Python Style

```python
# BENAR: type hints lengkap, return type jelas
def classify(self, text: str) -> Intent:
    ...

# SALAH: tidak ada type hint
def classify(self, text):
    ...

# BENAR: dataclass untuk data
@dataclass(frozen=True)
class Intent:
    action: str
    confidence: float = 1.0

# SALAH: dict untuk data yang punya shape tetap
intent = {"action": "memory", "confidence": 1.0}

# BENAR: named exception yang spesifik
class AIProviderUnavailableError(Exception): ...

# SALAH: raise generic Exception
raise Exception("AI not available")
```

### Aturan Komentar

- **Jangan tulis komentar yang menjelaskan WHAT** (kode yang baik sudah menjelaskan dirinya sendiri)
- **Tulis komentar hanya untuk WHY** yang tidak obvious: batasan tersembunyi, workaround bug spesifik, invariant subtle
- Docstring hanya untuk public API yang kompleks, maksimal 2 baris

### Penamaan

| Konteks | Konvensi | Contoh |
|---|---|---|
| Class | PascalCase | `OllamaAdapter`, `IntentClassifier` |
| Function/method | snake_case | `classify_intent`, `run_action` |
| Constant | UPPER_SNAKE | `MAX_REPLY_CHARS`, `DEFAULT_TIMEOUT` |
| Port/Protocol | Suffix `Port` atau tidak | `AIProvider`, `MessengerPort` |
| Adapter | Suffix `Adapter` | `OllamaAdapter`, `TelegramAdapter` |
| Action | Suffix `Action` | `ServerStatusAction`, `DiskAction` |
| Exception | Suffix `Error` | `AIProviderUnavailableError` |

---

## Menambah Action Baru

Setiap action baru **wajib** mengikuti pola ini:

```python
# app/actions/contoh.py
from dataclasses import dataclass
from app.domain.entities import ActionResult
from app.actions.base import Action

@dataclass
class ContohAction:
    """Satu kalimat: apa yang dilakukan action ini."""

    def execute(self, params: dict | None = None) -> ActionResult:
        # implementasi
        return ActionResult(output="...", action_name="contoh")

    @property
    def name(self) -> str:
        return "contoh"

    @property
    def description(self) -> str:
        return "Deskripsi singkat untuk prompt AI intent classifier"
```

Lalu daftarkan di `main.py` lewat `ActionRegistry`. **Jangan pernah** tambah action langsung ke `bot.py` atau hardcode nama action di tempat lain.

---

## Testing

Setiap kode baru **wajib** disertai unit test.

```
tests/
├── domain/
│   └── test_intent_classifier.py
├── actions/
│   └── test_server_action.py
└── adapters/
    └── test_ollama_adapter.py   # gunakan httpx mock, bukan hit Ollama nyata
```

**Aturan test:**
- Domain layer ditest **tanpa mock** (pure function, tidak ada dependencies)
- Adapter ditest dengan **mock HTTP/subprocess**, bukan resource nyata
- Gunakan `pytest` dan `pytest-asyncio`
- Nama test: `test_<kondisi>_<expected_result>`, contoh: `test_empty_text_returns_unknown_intent`
- Setiap bug fix **wajib** disertai regression test

Jalankan sebelum commit:
```bash
pytest tests/ -v
```

---

## Apa yang TIDAK Boleh Dilakukan

- **Jangan tambah fitur tanpa diminta** — tidak ada gold-plating
- **Jangan ubah arsitektur tanpa diskusi** — refactor besar butuh persetujuan eksplisit
- **Jangan hardcode credentials** — semua secret dari environment variable via `config.py`
- **Jangan gunakan `shell=True`** pada `subprocess` — gunakan list args
- **Jangan catch `Exception` secara generik** — tangkap exception spesifik
- **Jangan import adapter dari domain** — pelanggaran dependency rule hexagonal
- **Jangan buat file baru** jika bisa extend yang sudah ada

---

## Git Workflow & Konvensi PR

### Naming Branch

Format wajib: `<type>/<deskripsi-singkat-dengan-dash>`

| Type | Kapan dipakai |
|---|---|
| `feat/` | Fitur baru |
| `fix/` | Bug fix |
| `refactor/` | Refactoring tanpa perubahan behaviour |
| `chore/` | Maintenance: deps, config, CI |
| `docs/` | Dokumentasi saja |
| `test/` | Penambahan atau perbaikan test |
| `hotfix/` | Perbaikan urgent di production |

Contoh yang benar:
```
feat/docker-stats-action
fix/ollama-timeout-handling
refactor/split-intent-classifier
chore/upgrade-telegram-bot
```

Contoh yang salah:
```
update-bot          # tidak ada type prefix
feature-docker      # harus feat/, bukan feature-
Fix/something       # huruf kapital tidak diizinkan
```

### Format Judul PR / Commit (Conventional Commits)

```
<type>(<scope>): <deskripsi pendek>
```

- `scope` bersifat opsional, diisi nama modul yang diubah
- `deskripsi` menggunakan huruf kecil, tanpa titik di akhir
- Panjang maksimal 72 karakter

Contoh yang benar:
```
feat: tambah action monitoring docker stats
fix: handle timeout saat ollama tidak responsif
refactor(domain): pisah intent classifier ke file terpisah
chore: upgrade python-telegram-bot ke 22.8
test: unit test untuk ServerStatusAction
```

Contoh yang salah:
```
Update bot.py                         # tidak ada type
feat: Tambah Docker Stats Action.     # huruf kapital & titik di akhir
fixed the bug in ollama adapter       # tidak ada type prefix
```

### Aturan Merge

- **Tidak boleh push langsung ke `main`** — semua perubahan harus lewat PR
- **PR wajib lulus** semua check otomatis (branch name, PR title, lint, type-check, test) sebelum merge
- **Satu PR = satu concern** — jangan campur feat dan refactor dalam satu PR

### Workflow Harian

```bash
# Mulai fitur baru
git checkout -b feat/nama-fitur

# Kerjakan, lalu sebelum push:
make check                           # lint + type-check + test wajib hijau

# Push dan buat PR
git push origin feat/nama-fitur
# Buat PR di GitHub → GitHub Actions otomatis validasi branch + title + kode
# Setelah merge ke main → CI/CD otomatis deploy ke VPS
```

---

## Referensi Arsitektur

- Hexagonal Architecture: Alistair Cockburn (2005)
- Clean Architecture: Robert C. Martin
- Python typing best practices: PEP 544 (Protocols), PEP 681 (dataclass)
