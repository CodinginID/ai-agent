"""Unit tests for app/safety/redact.py -- redact_secrets()."""

from __future__ import annotations

import pytest

from app.safety.redact import redact_secrets


class TestRedactSecrets:
    """Tests for redact_secrets."""

    def test_empty_input(self) -> None:
        assert redact_secrets("") == ""

    def test_none_input(self) -> None:
        assert redact_secrets(None) == ""

    def test_whitespace_only(self) -> None:
        assert redact_secrets("   ") == "   "

    def test_no_secrets(self) -> None:
        assert redact_secrets("Hello world, nothing here.") == "Hello world, nothing here."

    def test_anthropic_api_key_replaced(self) -> None:
        text = f"url=https://api.example.com key=sk-ant-abc123def456ghi789jkl012mno345 done"
        result = redact_secrets(text)
        assert "sk-ant-" not in result
        assert "***REDACTED***" in result

    def test_ghp_github_token_replaced(self) -> None:
        text = f"token=ghp_ABCDEFghijklmnopqrstuvwxyz1234567890"
        result = redact_secrets(text)
        assert "ghp_" not in result
        assert "***REDACTED***" in result

    def test_telegram_bot_token_replaced(self) -> None:
        text = "bot=123456789:AAabcdefGHIJKLMNOPQRSTUVWXyz_123456789"
        result = redact_secrets(text)
        assert "***REDACTED***" in result

    def test_google_oauth_client_secret_replaced(self) -> None:
        text = '"client_secret": "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890abcd"'
        result = redact_secrets(text)
        assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in result
        assert "***REDACTED***" in result

    def test_antdropic_api_key_env_var_replaced(self) -> None:
        text = "ANTHROPIC_API_KEY=sk-ant-abc123def456ghi789jkl012mno345"
        result = redact_secrets(text)
        assert "sk-ant-" not in result

    def test_github_token_env_var_replaced(self) -> None:
        text = "GITHUB_TOKEN=ghp_ABCDEFghijklmnopqrstuvwxyz1234567890"
        result = redact_secrets(text)
        assert "ghp_" not in result

    def test_telegram_bot_token_env_var_replaced(self) -> None:
        text = "TELEGRAM_BOT_TOKEN=123456789:AAabcdefGHIJKLMNOPQRSTUVWXyz_123456789"
        result = redact_secrets(text)
        assert "***REDACTED***" in result

    def test_admin_token_env_var_replaced(self) -> None:
        text = "ADMIN_TOKEN=s3cr3t_t0k3n_v4lu3_12345"
        result = redact_secrets(text)
        assert "***REDACTED***" in result

    def test_database_url_env_var_replaced(self) -> None:
        text = "DATABASE_URL=postgres://user:pass@localhost/db"
        result = redact_secrets(text)
        assert "***REDACTED***" in result

    def test_webhook_secret_replaced(self) -> None:
        text = "WEBHOOK_SECRET=webhook_xyz_12345"
        result = redact_secrets(text)
        assert "***REDACTED***" in result

    def test_idempotent_on_already_redacted(self) -> None:
        text = "key=***REDACTED***"
        assert redact_secrets(text) == text
        assert redact_secrets(redact_secrets(text)) == text

    def test_multiple_secrets_in_same_text(self) -> None:
        text = (
            "ANTHROPIC_API_KEY=sk-ant-abc123def456ghi789jkl012 "
            "GITHUB_TOKEN=ghp_ABCDEFghijklmnopqrstuvwxyz1234567890 "
            "TELEGRAM_BOT_TOKEN=123456789:AAabcdefGHIJKLMNOPQRSTUVWXyz_123456789"
        )
        result = redact_secrets(text)
        assert "***REDACTED***" in result
        assert result.count("***REDACTED***") >= 2

    def test_url_with_api_key_in_path_not_affected(self) -> None:
        """Short sk-ant- strings that don't match the 20+ char pattern are not redacted."""
        text = "https://api.example.com/sk-ant-short"
        result = redact_secrets(text)
        assert "sk-ant-short" in result

    def test_partial_env_var_name_not_affected(self) -> None:
        """ENV_VAR that is not a known secret key should not be redacted."""
        text = "NORMAL_VARIABLE=hello123"
        result = redact_secrets(text)
        assert "hello123" in result

    def test_case_insensitive_env_var_match(self) -> None:
        """ENV var names should be matched case-insensitively."""
        text = "github_token=ghp_ABCDEFghijklmnopqrstuvwxyz1234567890"
        result = redact_secrets(text)
        assert "***REDACTED***" in result

    def test_log_line_simulation(self) -> None:
        """Simulate a realistic log line containing a URL and API key."""
        log_line = (
            '2026-08-06 10:00:00 DEBUG ollama chat: url=http://localhost:11434 '
            'api_key=sk-ant-abc123def456ghi789jkl012mno345 timeout=60'
        )
        result = redact_secrets(log_line)
        assert "sk-ant-" not in result
        assert "***REDACTED***" in result
        assert "http://localhost:11434" in result

    def test_error_message_with_token(self) -> None:
        """Simulate an error message containing a token."""
        error_msg = "Request failed: invalid ghp_ABCDEFghijklmnopqrstuvwxyz1234567890 token"
        result = redact_secrets(error_msg)
        assert "ghp_" not in result
        assert "***REDACTED***" in result

    def test_headers_dict_string_replaced(self) -> None:
        """Headers serialized as a string should have secrets redacted."""
        headers_str = '{"Authorization": "Bearer ghp_ABCDEFghijklmnopqrstuvwxyz1234567890"}'
        result = redact_secrets(headers_str)
        assert "ghp_" not in result
        assert "***REDACTED***" in result

    def test_env_vars_from_dotenv_format(self) -> None:
        """Common .env file content should be redacted."""
        env_content = (
            "ANTHROPIC_API_KEY=sk-ant-abc123def456ghi789jkl012mno345\n"
            "GITHUB_TOKEN=ghp_ABCDEFghijklmnopqrstuvwxyz1234567890\n"
            "TELEGRAM_BOT_TOKEN=987654321:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "ADMIN_TOKEN=supersecret123\n"
        )
        result = redact_secrets(env_content)
        assert "sk-ant-" not in result
        assert "ghp_" not in result
        assert "***REDACTED***" in result

    def test_google_oauth_secret_in_json_config(self) -> None:
        """Google OAuth client secret embedded in JSON config."""
        json_config = (
            '{"web": {"client_secret": "ABCDEF-ghijklmnop123456789", '
            '"client_id": "123456.apps.googleusercontent.com"}}'
        )
        result = redact_secrets(json_config)
        assert "ABCDEF-ghijklmnop123456789" not in result
        assert "***REDACTED***" in result
