from app.domain.agents import AgentCapability, resolve_agent_roles


def test_ready_capability_returns_ready_status() -> None:
    capability = AgentCapability(
        agent_id="codex",
        display_name="Codex",
        provider="openai",
        role_hint="engineer",
        enabled=True,
        available=True,
    )

    assert capability.ready is True
    assert capability.status == "ready"


def test_installed_disabled_capability_returns_installed_disabled_status() -> None:
    capability = AgentCapability(
        agent_id="claude",
        display_name="Claude",
        provider="anthropic",
        role_hint="reviewer",
        enabled=False,
        available=True,
    )

    assert capability.ready is False
    assert capability.status == "installed_disabled"


def test_resolve_agent_roles_marks_unknown_agent_as_not_ready() -> None:
    assignments = resolve_agent_roles(capabilities=(), assignments={"architect": "glm"})

    assert assignments[0].role == "architect"
    assert assignments[0].agent_id == "glm"
    assert assignments[0].ready is False
    assert assignments[0].status == "unknown_agent"


def test_resolve_agent_roles_uses_capability_status() -> None:
    capability = AgentCapability(
        agent_id="codex",
        display_name="Codex",
        provider="openai",
        role_hint="engineer",
        enabled=True,
        available=False,
    )

    assignments = resolve_agent_roles(
        capabilities=(capability,),
        assignments={"engineer": "codex"},
    )

    assert assignments[0].ready is False
    assert assignments[0].status == "enabled_missing"
