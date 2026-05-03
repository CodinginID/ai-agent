from app.adapters.agent_discovery import CliAgentDefinition, CliAgentDiscoveryAdapter


def test_cli_agent_discovery_marks_existing_binary_as_available() -> None:
    adapter = CliAgentDiscoveryAdapter(
        definitions=(
            CliAgentDefinition(
                agent_id="codex",
                display_name="Codex",
                provider="openai",
                role_hint="engineer",
                executable="codex",
                enabled=True,
            ),
        ),
        executable_finder=lambda executable: f"/usr/local/bin/{executable}",
    )

    capabilities = adapter.discover()

    assert capabilities[0].agent_id == "codex"
    assert capabilities[0].available is True
    assert capabilities[0].path == "/usr/local/bin/codex"


def test_cli_agent_discovery_marks_missing_binary_as_unavailable() -> None:
    adapter = CliAgentDiscoveryAdapter(
        definitions=(
            CliAgentDefinition(
                agent_id="claude",
                display_name="Claude",
                provider="anthropic",
                role_hint="reviewer",
                executable="claude",
                enabled=True,
            ),
        ),
        executable_finder=lambda _: None,
    )

    capabilities = adapter.discover()

    assert capabilities[0].agent_id == "claude"
    assert capabilities[0].available is False
    assert capabilities[0].status == "enabled_missing"
