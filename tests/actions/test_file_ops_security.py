"""File-ops sandbox security — symlink escape & traversal (Fase 0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.actions.file_ops import (
    FileAccessDeniedError,
    ReadFileAction,
    _resolve_safe,
)


def test_symlink_file_escaping_root_is_denied(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("TOP SECRET")
    (root / "escape").symlink_to(outside)  # symlink di dalam root → file di luar

    with pytest.raises(FileAccessDeniedError):
        _resolve_safe(str(root / "escape"), (root,))


def test_symlinked_dir_escape_is_denied(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside_dir = tmp_path / "etc"
    outside_dir.mkdir()
    (outside_dir / "passwd").write_text("root:x:0:0")
    (root / "evil").symlink_to(outside_dir)

    with pytest.raises(FileAccessDeniedError):
        _resolve_safe(str(root / "evil" / "passwd"), (root,))


def test_normal_path_inside_root_allowed(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    (root / "a.txt").write_text("hi")
    resolved = _resolve_safe(str(root / "a.txt"), (root,))
    assert resolved.name == "a.txt"


def test_dotdot_rejected(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    with pytest.raises(FileAccessDeniedError):
        _resolve_safe("../etc/passwd", (root,))


def test_read_action_denies_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("SECRET_CONTENT")
    (root / "leak").symlink_to(outside)

    out = ReadFileAction(allowed_roots=(root,)).execute({"path": str(root / "leak")})
    assert "Akses ditolak" in out
    assert "SECRET_CONTENT" not in out
