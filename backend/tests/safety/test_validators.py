"""Unit tests for app/safety/validators.py — validate_input()."""

from __future__ import annotations

import pytest

from app.safety.validators import validate_input


class TestValidateInput:
    """Tests for validate_input — length and path traversal."""

    def test_valid_short_input_returns_none(self) -> None:
        assert validate_input("halo") is None
        assert validate_input("  test  ") is None
        assert validate_input("hello world 123") is None

    def test_empty_input_returns_error(self) -> None:
        assert validate_input("") is not None
        assert validate_input("   ") is not None
        assert validate_input("") == "Input kosong."
        assert validate_input("   ") == "Input kosong."

    def test_non_string_input_returns_error(self) -> None:
        assert validate_input(123) is not None
        assert validate_input(None) is not None
        assert validate_input([]) is not None

    def test_max_length_boundary(self) -> None:
        text = "a" * 10000
        assert validate_input(text) is None

    def test_max_length_exceeded(self) -> None:
        text = "a" * 10001
        result = validate_input(text)
        assert result is not None
        assert "terlalu panjang" in result
        assert "10000" in result

    def test_custom_max_length(self) -> None:
        text = "a" * 101
        result = validate_input(text, max_length=100)
        assert result is not None
        assert "100" in result

    def test_traversal_semicolon_dot_slash(self) -> None:
        assert validate_input("/etc/../passwd") is not None
        assert "path traversal" in validate_input("/etc/../passwd").lower()

    def test_traversal_backslash_dot_slash(self) -> None:
        assert validate_input("..\\windows") is not None

    def test_traversal_in_middle(self) -> None:
        assert validate_input("hello ../etc") is not None

    def test_traversal_in_end(self) -> None:
        assert validate_input("data ../secret") is not None

    def test_normal_text_with_slash_is_ok(self) -> None:
        assert validate_input("http://example.com/path") is None
        assert validate_input("a/b/c/d") is None

    def test_triple_dot_is_ok(self) -> None:
        assert validate_input("...normal") is None
        assert validate_input("abc.def.ghi") is None
