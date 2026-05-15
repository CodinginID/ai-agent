from __future__ import annotations

from app.adapters.agent_discovery import CliAgentDefinition, CliAgentDiscoveryAdapter
from app.config import settings
from app.domain.agents import AgentCapability, AgentRoleAssignment, resolve_agent_roles
from app.handlers.agents import normalized_codex_sandbox


def qwen_capability() -> AgentCapability:
    return AgentCapability(
        agent_id="qwen",
        display_name="Qwen/Ollama",
        provider="ollama",
        role_hint="orchestrator",
        enabled=True,
        available=bool(settings.qwen_url and settings.qwen_model),
        path=settings.qwen_url,
        model=settings.qwen_model,
        access_mode="controller-only",
        description="Orchestrator, intent parser, planner, and result analyzer",
    )


def discover_agent_capabilities() -> tuple[AgentCapability, ...]:
    cli_agents = (
        CliAgentDefinition(
            agent_id="codex",
            display_name="Codex",
            provider="openai",
            role_hint="engineer",
            executable=settings.codex_bin,
            enabled=settings.enable_codex,
            model=settings.codex_model or None,
            access_mode=normalized_codex_sandbox() or settings.codex_sandbox,
            description="Code editing and engineering worker",
        ),
        CliAgentDefinition(
            agent_id="claude",
            display_name="Claude",
            provider="anthropic",
            role_hint="reviewer",
            executable=settings.claude_bin,
            enabled=settings.enable_claude,
            model=settings.claude_model or None,
            access_mode=(
                f"permission={settings.claude_permission_mode}, "
                f"tools={settings.claude_tools or settings.claude_allowed_tools or 'default'}"
            ),
            description="Review and code reasoning worker",
        ),
        CliAgentDefinition(
            agent_id="glm",
            display_name="GLM",
            provider="zhipu",
            role_hint="architect",
            executable=settings.glm_bin,
            enabled=settings.enable_glm,
            model=settings.glm_model or None,
            access_mode=settings.glm_access_mode,
            description="Architecture and planning worker",
        ),
    )
    discovered = CliAgentDiscoveryAdapter(cli_agents).discover()
    return (qwen_capability(), *discovered)


def agent_role_assignments(
    capabilities: tuple[AgentCapability, ...],
) -> tuple[AgentRoleAssignment, ...]:
    return resolve_agent_roles(
        capabilities=capabilities,
        assignments={
            "orchestrator": "qwen",
            "engineer": settings.agent_role_engineer,
            "architect": settings.agent_role_architect,
            "reviewer": settings.agent_role_reviewer,
        },
    )


def format_agent_capability(capability: AgentCapability) -> list[str]:
    location = capability.path or "not found"
    enabled = "yes" if capability.enabled else "no"
    available = "yes" if capability.available else "no"
    lines = [
        f"- {capability.display_name} ({capability.agent_id}): {capability.status}",
        f"  provider: {capability.provider}",
        f"  role hint: {capability.role_hint}",
        f"  enabled: {enabled}",
        f"  available: {available}",
        f"  location: {location}",
    ]
    if capability.model:
        lines.append(f"  model: {capability.model}")
    if capability.access_mode:
        lines.append(f"  access: {capability.access_mode}")
    return lines


def agent_status_text() -> str:
    capabilities = discover_agent_capabilities()
    assignments = agent_role_assignments(capabilities)
    lines = [
        "Agent registry",
        f"Admin restriction: {'nonaktif' if settings.allow_unrestricted_access else 'aktif'}",
        f"Agent workdir: {settings.agent_workdir}",
        f"Agent timeout: {settings.agent_timeout}s",
        "",
        "Role assignments:",
    ]

    for assignment in assignments:
        marker = "ready" if assignment.ready else "not ready"
        lines.append(
            f"- {assignment.role}: {assignment.agent_id} ({marker}, {assignment.status})"
        )
        lines.append(f"  detail: {assignment.detail}")

    lines.extend(["", "Registered agents:"])
    for capability in capabilities:
        lines.extend(format_agent_capability(capability))

    return "\n".join(lines)
