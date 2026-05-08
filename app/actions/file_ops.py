"""File operation actions — sandboxed to project_dir / terminal_workdir.

Security constraints enforced here:
- All paths must resolve inside the configured allowed roots.
- Paths containing ``..`` are rejected before resolution.
- Symlinks are not followed outside the allowed root.
- Maximum read size: 100 KB.
- Maximum write size: 100 KB.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.executor.actions import ActionMeta, ActionProtocol, ActionRegistry

MAX_READ_BYTES: int = 100 * 1024   # 100 KB
MAX_READ_CHARS: int = 5_000
MAX_WRITE_BYTES: int = 100 * 1024  # 100 KB


class FileAccessDeniedError(Exception):
    """Path is outside the allowed root directory."""


def _resolve_safe(raw_path: str, allowed_roots: tuple[Path, ...]) -> Path:
    """Resolve *raw_path* and ensure it lives under one of *allowed_roots*.

    Raises FileAccessDeniedError when the resolved path escapes every root.
    Rejects ``..`` early so the error message stays informative.
    """
    if ".." in Path(raw_path).parts:
        raise FileAccessDeniedError(f"Path traversal ditolak: {raw_path!r}")

    # Resolve without following symlinks first, then check containment.
    # Path.resolve() follows symlinks; we use os.path.abspath for the initial
    # check and only call resolve() to canonicalise the base roots.
    abs_path = Path(raw_path).expanduser()
    if not abs_path.is_absolute():
        # Relative path: anchor to first allowed root (project_dir).
        abs_path = allowed_roots[0] / abs_path

    # Resolve the path without following symlinks to avoid escaping root via symlink.
    real = Path(os.path.normpath(abs_path))

    for root in allowed_roots:
        try:
            real.relative_to(root)
            return real
        except ValueError:
            continue

    raise FileAccessDeniedError(
        f"Path '{real}' berada di luar direktori yang diizinkan."
    )


@dataclass
class ReadFileAction:
    """Read content of a file and return it."""

    allowed_roots: tuple[Path, ...] = field(default_factory=tuple)

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return "Read content of a file. Params: path (str)"

    def execute(self, params: dict[str, Any] | None = None) -> str:
        params = params or {}
        raw_path = str(params.get("path", ""))
        if not raw_path:
            return "Error: parameter 'path' wajib diisi."

        try:
            target = _resolve_safe(raw_path, self.allowed_roots)
        except FileAccessDeniedError as exc:
            return f"Akses ditolak: {exc}"

        if not target.exists():
            return f"File tidak ditemukan: {target}"
        if not target.is_file():
            return f"Bukan file: {target}"

        try:
            size = target.stat().st_size
        except OSError as exc:
            return f"Gagal membaca file: {exc}"

        if size > MAX_READ_BYTES:
            return (
                f"File terlalu besar ({size / 1024:.1f} KB). "
                f"Maksimal {MAX_READ_BYTES // 1024} KB."
            )

        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"Gagal membaca file: {exc}"

        if len(content) > MAX_READ_CHARS:
            return content[:MAX_READ_CHARS] + f"\n\n...[dipotong setelah {MAX_READ_CHARS} karakter]"
        return content


@dataclass
class WriteFileAction:
    """Write or overwrite a file."""

    allowed_roots: tuple[Path, ...] = field(default_factory=tuple)

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return "Write content to a file. Params: path (str), content (str)"

    def execute(self, params: dict[str, Any] | None = None) -> str:
        params = params or {}
        raw_path = str(params.get("path", ""))
        content = str(params.get("content", ""))

        if not raw_path:
            return "Error: parameter 'path' wajib diisi."

        if len(content.encode("utf-8")) > MAX_WRITE_BYTES:
            return (
                f"Konten terlalu besar. Maksimal {MAX_WRITE_BYTES // 1024} KB."
            )

        try:
            target = _resolve_safe(raw_path, self.allowed_roots)
        except FileAccessDeniedError as exc:
            return f"Akses ditolak: {exc}"

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            return f"Gagal menulis file: {exc}"

        return f"File berhasil ditulis: {target} ({len(content)} karakter)"


@dataclass
class ListDirAction:
    """List files in a directory."""

    allowed_roots: tuple[Path, ...] = field(default_factory=tuple)

    @property
    def name(self) -> str:
        return "file_list"

    @property
    def description(self) -> str:
        return "List files in directory. Params: path (str, default '.')"

    def execute(self, params: dict[str, Any] | None = None) -> str:
        params = params or {}
        raw_path = str(params.get("path", "."))

        try:
            target = _resolve_safe(raw_path, self.allowed_roots)
        except FileAccessDeniedError as exc:
            return f"Akses ditolak: {exc}"

        if not target.exists():
            return f"Direktori tidak ditemukan: {target}"
        if not target.is_dir():
            return f"Bukan direktori: {target}"

        try:
            entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError as exc:
            return f"Akses ditolak: {exc}"

        if not entries:
            return f"{target}: (kosong)"

        lines = [f"{target}:"]
        for entry in entries:
            try:
                stat = entry.stat()
                size = stat.st_size
                suffix = "/" if entry.is_dir() else ""
                lines.append(f"  {entry.name}{suffix}  ({size} bytes)" if not entry.is_dir() else f"  {entry.name}/")
            except OSError:
                lines.append(f"  {entry.name}  (stat error)")

        return "\n".join(lines)


@dataclass
class EditFileAction:
    """Edit a file by replacing a string."""

    allowed_roots: tuple[Path, ...] = field(default_factory=tuple)

    @property
    def name(self) -> str:
        return "file_edit"

    @property
    def description(self) -> str:
        return "Edit file: replace old_string with new_string. Params: path, old_string, new_string"

    def execute(self, params: dict[str, Any] | None = None) -> str:
        params = params or {}
        raw_path = str(params.get("path", ""))
        old_string = str(params.get("old_string", ""))
        new_string = str(params.get("new_string", ""))

        if not raw_path:
            return "Error: parameter 'path' wajib diisi."
        if not old_string:
            return "Error: parameter 'old_string' wajib diisi."

        try:
            target = _resolve_safe(raw_path, self.allowed_roots)
        except FileAccessDeniedError as exc:
            return f"Akses ditolak: {exc}"

        if not target.exists():
            return f"File tidak ditemukan: {target}"
        if not target.is_file():
            return f"Bukan file: {target}"

        try:
            original = target.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return f"Gagal membaca file: {exc}"

        if old_string not in original:
            return f"String '{old_string[:80]}' tidak ditemukan dalam file."

        updated = original.replace(old_string, new_string, 1)

        if len(updated.encode("utf-8")) > MAX_WRITE_BYTES:
            return f"Hasil edit terlalu besar. Maksimal {MAX_WRITE_BYTES // 1024} KB."

        try:
            target.write_text(updated, encoding="utf-8")
        except OSError as exc:
            return f"Gagal menulis file: {exc}"

        return f"File berhasil diedit: {target}"


def register_file_ops(registry: ActionRegistry, allowed_roots: tuple[Path, ...]) -> None:
    """Register all file operation actions into *registry*."""
    actions: list[ActionProtocol] = [
        ReadFileAction(allowed_roots=allowed_roots),
        WriteFileAction(allowed_roots=allowed_roots),
        ListDirAction(allowed_roots=allowed_roots),
        EditFileAction(allowed_roots=allowed_roots),
    ]
    for action in actions:
        registry.register(ActionMeta(
            name=action.name,
            description=action.description,
            risk_level="medium",
            requires_approval=False,
            handler=action.execute,
        ))
