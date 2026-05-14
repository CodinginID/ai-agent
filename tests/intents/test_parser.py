"""Unit tests for IntentParser and local intent heuristics."""

from __future__ import annotations

from app.intents.parser import IntentParser, _parse_local
from app.intents.schemas import Intent

_PROJECT_ID = "test-proj"


# ── Local parsing (no AI call needed) ─────────────────────────────────────────


class TestGreetingAndChat:
    def test_greeting_halo(self) -> None:
        intent = _parse_local("halo", _PROJECT_ID)
        assert intent == Intent(
            intent="chat", project_id=_PROJECT_ID, confidence=1.0,
            requires_approval=False, parameters={}, reason="Greeting or general chat",
        )

    def test_greeting_hi(self) -> None:
        intent = _parse_local("hi", _PROJECT_ID)
        assert intent.intent == "chat"

    def test_greeting_assalamualaikum(self) -> None:
        intent = _parse_local("assalamualaikum", _PROJECT_ID)
        assert intent.intent == "chat"

    def test_question_without_action_keyword(self) -> None:
        intent = _parse_local("apa itu docker?", _PROJECT_ID)
        assert intent.intent == "chat"

    def test_jelaskan_prefix(self) -> None:
        intent = _parse_local("jelaskan hexagonal architecture", _PROJECT_ID)
        assert intent.intent == "chat"

    def test_conversation_phrase_diskusi(self) -> None:
        intent = _parse_local("mau diskusi soal docker", _PROJECT_ID)
        assert intent.intent == "chat"

    def test_conversation_phrase_kasih_saran(self) -> None:
        intent = _parse_local("kasih saran buat deployment", _PROJECT_ID)
        assert intent.intent == "chat"


class TestServerActions:
    def test_server_status(self) -> None:
        intent = _parse_local("cek status server", _PROJECT_ID)
        assert intent.intent == "server_status"
        assert intent.requires_approval is False

    def test_server_uptime(self) -> None:
        intent = _parse_local("uptime server gimana", _PROJECT_ID)
        assert intent.intent == "server_status"

    def test_memory_usage(self) -> None:
        intent = _parse_local("cek ram", _PROJECT_ID)
        assert intent.intent == "memory"

    def test_memory_swap(self) -> None:
        intent = _parse_local("swap usage", _PROJECT_ID)
        assert intent.intent == "memory"

    def test_disk_usage(self) -> None:
        intent = _parse_local("cek disk", _PROJECT_ID)
        assert intent.intent == "disk"

    def test_processes(self) -> None:
        intent = _parse_local("proses yang jalan", _PROJECT_ID)
        assert intent.intent == "processes"

    def test_top_processes(self) -> None:
        intent = _parse_local("top processes", _PROJECT_ID)
        assert intent.intent == "processes"

    def test_whoami(self) -> None:
        intent = _parse_local("whoami", _PROJECT_ID)
        assert intent.intent == "whoami"

    def test_list_files(self) -> None:
        intent = _parse_local("list file", _PROJECT_ID)
        assert intent.intent == "list_files"

    def test_hostname(self) -> None:
        intent = _parse_local("hostname server", _PROJECT_ID)
        assert intent.intent == "whoami"


class TestDockerActions:
    def test_docker_ps(self) -> None:
        intent = _parse_local("container yang jalan", _PROJECT_ID)
        assert intent.intent == "docker_ps"

    def test_docker_images(self) -> None:
        intent = _parse_local("docker images", _PROJECT_ID)
        assert intent.intent == "docker_images"

    def test_docker_stats(self) -> None:
        intent = _parse_local("docker stats container", _PROJECT_ID)
        assert intent.intent == "docker_stats"

    def test_docker_restart_requires_approval(self) -> None:
        intent = _parse_local("docker restart", _PROJECT_ID)
        assert intent.intent == "docker_restart"
        assert intent.requires_approval is True

    def test_docker_logs(self) -> None:
        intent = _parse_local("docker logs", _PROJECT_ID)
        assert intent.intent == "docker_logs"


class TestGitActions:
    def test_git_status(self) -> None:
        intent = _parse_local("git status", _PROJECT_ID)
        assert intent.intent == "git_status"
        assert intent.requires_approval is False

    def test_git_pull_requires_approval(self) -> None:
        intent = _parse_local("git pull", _PROJECT_ID)
        assert intent.intent == "git_pull"
        assert intent.requires_approval is True


class TestDeployActions:
    def test_deploy_requires_approval(self) -> None:
        intent = _parse_local("deploy sekarang", _PROJECT_ID)
        assert intent.intent == "deploy"
        assert intent.requires_approval is True

    def test_rollback_requires_approval(self) -> None:
        intent = _parse_local("rollback deploy", _PROJECT_ID)
        assert intent.intent == "rollback"
        assert intent.requires_approval is True

    def test_service_health_check(self) -> None:
        intent = _parse_local("health check url https://example.com", _PROJECT_ID)
        assert intent.intent == "service_health_check"
        assert intent.requires_approval is False


class TestDockerComposeActions:
    def test_compose_ps(self) -> None:
        intent = _parse_local("compose ps", _PROJECT_ID)
        assert intent.intent == "docker_compose_ps"

    def test_compose_pull(self) -> None:
        intent = _parse_local("compose pull", _PROJECT_ID)
        assert intent.intent == "docker_compose_pull"
        assert intent.requires_approval is True

    def test_compose_build(self) -> None:
        intent = _parse_local("compose build", _PROJECT_ID)
        assert intent.intent == "docker_compose_build"
        assert intent.requires_approval is True

    def test_compose_restart(self) -> None:
        intent = _parse_local("compose restart", _PROJECT_ID)
        assert intent.intent == "docker_compose_restart"
        assert intent.requires_approval is True


class TestAgentRoleTriggers:
    def test_code_prefix(self) -> None:
        intent = _parse_local("/code refactor function X", _PROJECT_ID)
        assert intent.intent == "agent_code"

    def test_refactor_prefix(self) -> None:
        intent = _parse_local("/refactor module bot", _PROJECT_ID)
        assert intent.intent == "agent_code"

    def test_review_prefix(self) -> None:
        intent = _parse_local("/review PR #5", _PROJECT_ID)
        assert intent.intent == "agent_review"

    def test_architect_prefix(self) -> None:
        intent = _parse_local("/architect design auth", _PROJECT_ID)
        assert intent.intent == "agent_architect"

    def test_code_bare(self) -> None:
        intent = _parse_local("/code", _PROJECT_ID)
        assert intent.intent == "agent_code"


class TestUnknownIntent:
    def test_random_text(self) -> None:
        result = _parse_local("saya lapar", _PROJECT_ID)
        assert result is None

    def test_empty_after_normalize(self) -> None:
        result = _parse_local("   ", _PROJECT_ID)
        assert result is None


# ── Word boundary helpers ─────────────────────────────────────────────────────


class TestWordBoundary:
    def test_disk_vs_diskusi(self) -> None:
        """'diskusi' should NOT match 'disk' action via word-boundary."""
        result = _parse_local("saya ingin diskusi soal server", _PROJECT_ID)
        # Chat phrase match wins before disk keyword
        assert result is None or result.intent == "chat"

    def test_disk_standalone_matches(self) -> None:
        result = _parse_local("cek disk usage", _PROJECT_ID)
        assert result.intent == "disk"


# ── AI fallback path ──────────────────────────────────────────────────────────


class TestIntentParserAIFallback:
    def test_uses_ai_when_local_unknown(self) -> None:
        def mock_qwen(prompt: str) -> str:
            return '{"intent":"processes","confidence":0.9,"reason":"AI matched"}'

        parser = IntentParser(mock_qwen)
        # Input sengaja tidak match heuristic lokal apa pun → harus jatuh ke AI.
        intent = parser.parse("buka kulkas", "proj-1")
        assert intent.intent == "processes"
        assert intent.confidence == 0.9
        assert intent.reason == "AI matched"

    def test_skips_ai_when_local_match(self) -> None:
        called = False

        def mock_qwen(prompt: str) -> str:
            nonlocal called
            called = True
            return '{"intent":"server_status","confidence":1.0,"reason":""}'

        parser = IntentParser(mock_qwen)
        intent = parser.parse("cek ram", "proj-1")
        assert intent.intent == "memory"
        assert called is False

    def test_returns_unknown_on_ai_failure(self) -> None:
        def mock_qwen(prompt: str) -> str:
            raise ConnectionError("timeout")

        parser = IntentParser(mock_qwen)
        # Input tidak match heuristic lokal → fallback ke AI → AI gagal → unknown.
        intent = parser.parse("buka pintu mobil", "proj-1")
        assert intent.intent == "unknown"

    def test_returns_unknown_on_invalid_json_from_ai(self) -> None:
        def mock_qwen(prompt: str) -> str:
            return "bukan json valid"

        parser = IntentParser(mock_qwen)
        intent = parser.parse("buka kulkas", "proj-1")
        assert intent.intent == "unknown"

    def test_returns_unknown_on_invalid_intent_from_ai(self) -> None:
        def mock_qwen(prompt: str) -> str:
            return '{"intent":"nonexistent_action","confidence":0.5,"reason":""}'

        parser = IntentParser(mock_qwen)
        intent = parser.parse("terbang", "proj-1")
        assert intent.intent == "unknown"

    def test_maintains_requires_approval_for_risk(self) -> None:
        def mock_qwen(prompt: str) -> str:
            return '{"intent":"deploy","confidence":0.9,"requires_approval":false,"reason":"AI","parameters":{}}'

        parser = IntentParser(mock_qwen)
        intent = parser.parse("jalankan deployment", "proj-1")
        assert intent.intent == "deploy"
        # HIGH_RISK intent always forces requires_approval=True
        assert intent.requires_approval is True

    def test_parses_parameters_from_ai(self) -> None:
        def mock_qwen(prompt: str) -> str:
            return (
                '{"intent":"docker_restart","confidence":0.9,"requires_approval":true,'
                '"reason":"","parameters":{"container_name":"web"}}'
            )

        parser = IntentParser(mock_qwen)
        # Input tanpa kata kunci lokal supaya fallback ke AI yang mengisi parameters.
        intent = parser.parse("kerjakan misi", "proj-1")
        assert intent.intent == "docker_restart"
        assert intent.parameters == {"container_name": "web"}

    def test_local_match_returns_correct_project_id(self) -> None:
        intent = _parse_local("cek memory", "my-proj-id")
        assert intent.project_id == "my-proj-id"
