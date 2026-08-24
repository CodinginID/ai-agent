# Panduan Kontribusi

Terima kasih atas minat Anda untuk berkontribusi pada proyek ini. Berikut panduan langkah demi langkah untuk mulai berkontribusi secara lokal.

---

## 1. Setup Lingkungan Lokal

```bash
# Buat virtual environment
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# atau: .venv\Scripts\activate   # Windows

# Install dependensi produksi dan pengembangan
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

---

## 2. Menjalankan Aplikasi (Development)

```bash
# Opsi 1: Jalankan langsung
python -m app.main

# Opsi 2: Jalankan lewat dev script
./dev.sh
```

---

## 3. Menjalankan Test

```bash
pytest tests/ -v
```

Semua test wajib lulus sebelum mengajukan PR.

---

## 4. Linting dan Type Checking

```bash
# Linting (ruff)
ruff check app/ tests/

# Type checking (mypy)
mypy app/
```

Kedua tool wajib bersih (no errors) sebelum PR disetujui.

---

## 5. Membuat Pull Request

```bash
# 1. Buat branch baru dari main
git checkout main
git pull origin main
git checkout -b feat/nama-fitur

# 2. Kerjakan perubahan, lalu jalankan semua cek:
ruff check app/ tests/
mypy app/
pytest tests/ -v

# 3. Commit dengan pesan yang sesuai conventional commits
git add .
git commit -m "feat: deskripsi singkat perubahan"

# 4. Push dan buat PR
git push origin feat/nama-fitur
gh pr create --title "feat: deskripsi perubahan" --body "Penjelasan detail tentang perubahan ini."
```

### Checklist Sebelum Push

- [ ] `ruff check app/ tests/` bersih
- [ ] `mypy app/` bersih
- [ ] `pytest tests/ -v` semua lulus
- [ ] Commit message mengikuti Conventional Commits (`feat:`, `fix:`, `refactor:`, `test:`, `chore:`)

---

## Konvensi Tambahan

- **Jangan hardcode** kredensial atau secret — gunakan environment variable.
- **Satu PR = satu concern** — jangan campur beberapa fitur atau perbaikan dalam satu PR.
- **Tambahkan test** untuk setiap perubahan yang menyentuh business logic atau adapter baru.
- **Baca `CLAUDE.md`** di root repo sebelum mulai mengerjakan sesuatu yang kompleks.

---

Pertanyaan? Buka issue atau ajukan PR dan tim akan meninjau.
