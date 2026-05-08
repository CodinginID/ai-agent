"""Unit tests for app/actions/file_ops.py — uses temp directories, no real project_dir."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.actions.file_ops import (
    EditFileAction,
    FileAccessDeniedError,
    ListDirAction,
    ReadFileAction,
    WriteFileAction,
    _resolve_safe,
)

# ── _resolve_safe ──────────────────────────────────────────────────────────────

def test_resolve_safe_rejects_dotdot_in_path() -> None:
    with pytest.raises(FileAccessDeniedError, match="traversal"):
        _resolve_safe("../etc/passwd", (Path("/allowed"),))


def test_resolve_safe_rejects_path_outside_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    with pytest.raises(FileAccessDeniedError):
        _resolve_safe(str(tmp_path / "outside" / "file.txt"), (allowed,))


def test_resolve_safe_accepts_path_inside_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    target = allowed / "subdir" / "file.txt"
    result = _resolve_safe(str(target), (allowed,))
    assert result == target.resolve() or result == target


def test_resolve_safe_relative_path_anchors_to_first_root(tmp_path: Path) -> None:
    allowed = tmp_path / "project"
    allowed.mkdir()
    result = _resolve_safe("src/main.py", (allowed,))
    assert str(result).startswith(str(allowed))


# ── ReadFileAction ─────────────────────────────────────────────────────────────

def test_read_file_returns_content(tmp_path: Path) -> None:
    f = tmp_path / "hello.txt"
    f.write_text("Hello world", encoding="utf-8")

    action = ReadFileAction(allowed_roots=(tmp_path,))
    result = action.execute({"path": str(f)})

    assert result == "Hello world"


def test_read_file_missing_returns_error(tmp_path: Path) -> None:
    action = ReadFileAction(allowed_roots=(tmp_path,))
    result = action.execute({"path": str(tmp_path / "nonexistent.txt")})

    assert "tidak ditemukan" in result


def test_read_file_denied_outside_root(tmp_path: Path) -> None:
    inside = tmp_path / "inside"
    inside.mkdir()
    action = ReadFileAction(allowed_roots=(inside,))
    result = action.execute({"path": str(tmp_path / "outside.txt")})

    assert "ditolak" in result.lower()


def test_read_file_truncates_at_5000_chars(tmp_path: Path) -> None:
    f = tmp_path / "big.txt"
    f.write_text("x" * 6000, encoding="utf-8")

    action = ReadFileAction(allowed_roots=(tmp_path,))
    result = action.execute({"path": str(f)})

    assert "dipotong" in result
    assert len(result) < 6000


def test_read_file_missing_path_param_returns_error(tmp_path: Path) -> None:
    action = ReadFileAction(allowed_roots=(tmp_path,))
    result = action.execute({})
    assert "path" in result.lower()


# ── WriteFileAction ────────────────────────────────────────────────────────────

def test_write_file_creates_new_file(tmp_path: Path) -> None:
    action = WriteFileAction(allowed_roots=(tmp_path,))
    result = action.execute({"path": str(tmp_path / "new.txt"), "content": "data"})

    assert "berhasil" in result.lower()
    assert (tmp_path / "new.txt").read_text() == "data"


def test_write_file_overwrites_existing(tmp_path: Path) -> None:
    f = tmp_path / "existing.txt"
    f.write_text("old", encoding="utf-8")
    action = WriteFileAction(allowed_roots=(tmp_path,))
    action.execute({"path": str(f), "content": "new"})

    assert f.read_text() == "new"


def test_write_file_denied_outside_root(tmp_path: Path) -> None:
    inside = tmp_path / "inside"
    inside.mkdir()
    action = WriteFileAction(allowed_roots=(inside,))
    result = action.execute({"path": str(tmp_path / "escape.txt"), "content": "x"})

    assert "ditolak" in result.lower()


# ── ListDirAction ──────────────────────────────────────────────────────────────

def test_list_dir_returns_entries(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "sub").mkdir()

    action = ListDirAction(allowed_roots=(tmp_path,))
    result = action.execute({"path": str(tmp_path)})

    assert "a.txt" in result
    assert "sub" in result


def test_list_dir_default_dot_uses_first_root(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("")
    action = ListDirAction(allowed_roots=(tmp_path,))
    result = action.execute({})

    assert "readme.md" in result


def test_list_dir_nonexistent_returns_error(tmp_path: Path) -> None:
    action = ListDirAction(allowed_roots=(tmp_path,))
    result = action.execute({"path": str(tmp_path / "ghost")})
    assert "tidak ditemukan" in result


# ── EditFileAction ─────────────────────────────────────────────────────────────

def test_edit_file_replaces_string(tmp_path: Path) -> None:
    f = tmp_path / "code.py"
    f.write_text("x = 1\ny = 2\n", encoding="utf-8")

    action = EditFileAction(allowed_roots=(tmp_path,))
    result = action.execute({"path": str(f), "old_string": "x = 1", "new_string": "x = 99"})

    assert "berhasil" in result.lower()
    assert f.read_text() == "x = 99\ny = 2\n"


def test_edit_file_string_not_found_returns_error(tmp_path: Path) -> None:
    f = tmp_path / "code.py"
    f.write_text("x = 1\n", encoding="utf-8")

    action = EditFileAction(allowed_roots=(tmp_path,))
    result = action.execute({"path": str(f), "old_string": "z = 99", "new_string": "z = 0"})

    assert "tidak ditemukan" in result


def test_edit_file_replaces_only_first_occurrence(tmp_path: Path) -> None:
    f = tmp_path / "repeat.txt"
    f.write_text("aaa aaa aaa", encoding="utf-8")

    action = EditFileAction(allowed_roots=(tmp_path,))
    action.execute({"path": str(f), "old_string": "aaa", "new_string": "bbb"})

    content = f.read_text()
    assert content == "bbb aaa aaa"
