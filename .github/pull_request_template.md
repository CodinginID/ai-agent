## Tipe Perubahan

- [ ] `feat` — fitur baru
- [ ] `fix` — bug fix
- [ ] `refactor` — refactoring tanpa perubahan behaviour
- [ ] `chore` — maintenance (deps, config, CI)
- [ ] `docs` — dokumentasi saja
- [ ] `test` — penambahan atau perbaikan test
- [ ] `hotfix` — perbaikan urgent di production

## Deskripsi

<!-- Jelaskan APA yang berubah dan MENGAPA, bukan bagaimana -->

## Terkait Issue

Closes #

## Checklist

### Kode
- [ ] Tidak ada hardcoded credentials atau secret
- [ ] Semua fungsi baru memiliki type hint lengkap
- [ ] Tidak ada `shell=True` pada subprocess
- [ ] Tidak ada `except Exception` yang terlalu generik

### Arsitektur
- [ ] Domain layer tidak mengimport dari adapter layer
- [ ] Action baru mengikuti pola `Action` Protocol di `app/actions/base.py`
- [ ] Dependency injection dilakukan di `main.py`, bukan di dalam class

### Testing
- [ ] Ada unit test untuk setiap kode baru
- [ ] `make check` lulus tanpa error (lint + type-check + test)
- [ ] Bug fix disertai regression test

### Dokumentasi
- [ ] README diupdate jika ada perubahan cara install/pakai
- [ ] CLAUDE.md diupdate jika ada perubahan arsitektur atau aturan baru
