"""Unit tests untuk ``app.interfaces.cli``.

Use case di-mock lewat ``app.composition.build_use_case`` supaya test tidak
butuh Ollama atau database.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.domain.messaging import ChatEvent
from app.interfaces import cli as cli_module
from app.memory.models import Project


@pytest.fixture
def fake_project() -> Project:
    return Project(
        id="default",
        name="default",
        root_path="/tmp/repo",
        description="",
        created_at="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )


@pytest.fixture
def fake_store(fake_project: Project) -> MagicMock:
    store = MagicMock()
    store.get_active_project.return_value = fake_project
    store.get_active_project_id.return_value = fake_project.id
    store.list_projects.return_value = [fake_project]
    store.get_project.return_value = fake_project
    return store


# ── status ───────────────────────────────────────────────────────────────────


def test_status_human_output_contains_project_and_model(
    fake_store: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(cli_module, "_project_store", return_value=fake_store):
        rc = cli_module.main(["status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Project: default" in out
    assert "AI provider:" in out


def test_status_json_output_is_valid_json(
    fake_store: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(cli_module, "_project_store", return_value=fake_store):
        rc = cli_module.main(["--json", "status"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 0
    assert payload["project_name"] == "default"
    assert "ai_provider" in payload


# ── ask ──────────────────────────────────────────────────────────────────────


def test_ask_emits_final_text_and_exits_zero(
    fake_store: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    use_case = MagicMock()
    use_case.handle.return_value = iter([
        ChatEvent.intent_classified("chat", 0.9, "halo"),
        ChatEvent.text_chunk("halo "),
        ChatEvent.text_chunk("dunia"),
        ChatEvent.final("halo dunia"),
    ])
    with (
        patch.object(cli_module, "_project_store", return_value=fake_store),
        patch("app.composition.build_use_case", return_value=use_case),
    ):
        rc = cli_module.main(["ask", "halo"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "halo dunia" in out
    use_case.handle.assert_called_once()


def test_ask_propagates_error_event_to_nonzero_exit(
    fake_store: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    use_case = MagicMock()
    use_case.handle.return_value = iter([
        ChatEvent.error("ollama down"),
    ])
    with (
        patch.object(cli_module, "_project_store", return_value=fake_store),
        patch("app.composition.build_use_case", return_value=use_case),
    ):
        rc = cli_module.main(["ask", "halo"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "ollama down" in err


def test_ask_empty_text_returns_exit_2() -> None:
    rc = cli_module.main(["ask", "   "])
    assert rc == 2


def test_ask_json_mode_returns_structured_payload(
    fake_store: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    use_case = MagicMock()
    use_case.handle.return_value = iter([
        ChatEvent.intent_classified("chat", 0.9, "halo"),
        ChatEvent.final("halo dunia"),
    ])
    with (
        patch.object(cli_module, "_project_store", return_value=fake_store),
        patch("app.composition.build_use_case", return_value=use_case),
    ):
        rc = cli_module.main(["--json", "ask", "halo"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["final"] == "halo dunia"
    assert payload["intent"]["intent"] == "chat"


# ── run ──────────────────────────────────────────────────────────────────────


def test_run_blocks_command_denied_by_safety_policy(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = cli_module.main(["run", "rm -rf /tmp/foo"])
    err = capsys.readouterr().err
    assert rc == 3
    assert "safety policy" in err


def test_run_executes_allowed_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch(
        "app.handlers.process_runners.run_terminal_process",
        return_value="hello\n",
    ):
        rc = cli_module.main(["run", "echo hello"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "hello" in out


# ── project ──────────────────────────────────────────────────────────────────


def test_project_list_shows_active_marker(
    fake_store: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(cli_module, "_project_store", return_value=fake_store):
        rc = cli_module.main(["project", "list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "default" in out
    assert "*" in out


def test_project_use_unknown_returns_nonzero(
    fake_store: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_store.get_project.return_value = None
    with patch.object(cli_module, "_project_store", return_value=fake_store):
        rc = cli_module.main(["project", "use", "ghost"])
    err = capsys.readouterr().err
    assert rc == 4
    assert "ghost" in err


def test_project_use_switches_active(
    fake_store: MagicMock, fake_project: Project, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(cli_module, "_project_store", return_value=fake_store):
        rc = cli_module.main(["project", "use", "default"])
    assert rc == 0
    fake_store.set_active_project.assert_called_once_with(0, fake_project.id)
    assert "default" in capsys.readouterr().out


# ── context / tasks ──────────────────────────────────────────────────────────


def test_context_show_includes_project(
    fake_store: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch.object(cli_module, "_project_store", return_value=fake_store):
        rc = cli_module.main(["context", "show"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Project: default" in out


def test_tasks_list_placeholder(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli_module.main(["tasks", "list"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "task" in out.lower()


def test_tasks_list_json_returns_empty_list(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli_module.main(["--json", "tasks", "list"])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["tasks"] == []


# ── parser ───────────────────────────────────────────────────────────────────


def test_missing_subcommand_exits_with_argparse_error() -> None:
    with pytest.raises(SystemExit):
        cli_module.main([])


def test_parser_builds_without_side_effects() -> None:
    parser = cli_module._build_parser()
    assert parser.prog == "ai-agent"
