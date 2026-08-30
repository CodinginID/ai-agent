# app/interfaces/auth_pages.py
"""HTML page builders untuk flow login/pair (Google OAuth + TUI) — pure string
templating, tanpa dependensi lain. Dipisah dari ``auth.py`` supaya file itu
tidak membengkak (lihat CLAUDE.md: file < 500 baris)."""

from __future__ import annotations

import urllib.parse

_PAGE_STYLE = """
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; }
  .card { text-align: center; padding: 48px 40px; max-width: 440px; width: 100%; }
  .icon { font-size: 3rem; margin-bottom: 16px; }
  h1   { font-size: 1.6rem; margin-bottom: 10px; }
  p    { color: #94a3b8; font-size: 0.95rem; line-height: 1.6; }
  .meta { margin-top: 8px; font-size: 0.85rem; color: #64748b; }
  .dim  { margin-top: 28px; font-size: 0.8rem; color: #475569; }
  a    { color: #60a5fa; text-decoration: none; }
  .btn { display: inline-block; margin-top: 24px; padding: 12px 28px;
         background: #4285F4; color: #fff; border-radius: 6px;
         font-size: 0.95rem; font-weight: 500; text-decoration: none; }
  .btn:hover { background: #3367D6; }
  .err { color: #f87171; }
</style>
"""


def page(body: str) -> str:
    return f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>AI Agent</title>{_PAGE_STYLE}</head><body>{body}</body></html>"


def success_page(name: str, email: str, is_new: bool) -> str:
    greeting = "Akun berhasil dibuat" if is_new else "Selamat datang kembali"
    return page(f"""
<div class="card">
  <div class="icon">&#10003;</div>
  <h1 style="color:#4ade80">Login Berhasil</h1>
  <p>{greeting}, <strong>{name}</strong></p>
  <p class="meta">{email}</p>
  <p style="margin-top:20px">Buka Telegram dan kirim <strong>/start</strong> ke bot untuk mulai.</p>
  <p class="dim">Halaman ini bisa ditutup.</p>
</div>""")


def error_page(message: str) -> str:
    return page(f"""
<div class="card">
  <div class="icon">&#10007;</div>
  <h1 class="err">Login Gagal</h1>
  <p>{message}</p>
  <a class="btn" href="/auth/google/login">Coba Lagi</a>
  <p class="dim" style="margin-top:20px">Atau tutup halaman ini dan coba dari terminal.</p>
</div>""")


def login_page() -> str:
    return page("""
<div class="card">
  <div class="icon">&#128100;</div>
  <h1>AI Agent</h1>
  <p>Login untuk mengakses dan mendaftarkan akun kamu.</p>
  <a class="btn" href="/auth/google/login">Login dengan Google</a>
  <p class="dim" style="margin-top:20px">Akun Google kamu digunakan hanya untuk verifikasi identitas.</p>
</div>""")


def tui_success_page(name: str, email: str) -> str:
    return page(f"""
<div class="card">
  <div class="icon">&#10003;</div>
  <h1 style="color:#4ade80">TUI Terhubung</h1>
  <p>Hai, <strong>{name}</strong></p>
  <p class="meta">{email}</p>
  <p style="margin-top:20px">Kembali ke terminal — TUI sudah login otomatis.</p>
  <p class="dim" style="margin-top:20px">Halaman ini bisa ditutup.</p>
</div>""")


def tui_login_page(code: str) -> str:
    return page(f"""
<div class="card">
  <div class="icon">&#128187;</div>
  <h1>AI Agent TUI</h1>
  <p>Kode pair: <strong>{code}</strong></p>
  <p>Login dengan Google untuk hubungkan TUI di terminal kamu.</p>
  <a class="btn" href="/auth/google/login?tui_code={urllib.parse.quote(code)}">
    Login dengan Google
  </a>
  <p class="dim" style="margin-top:20px">Kode ini berlaku 10 menit.</p>
</div>""")
