from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.adapters.database.base import Base


def uuid_str() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    telegram_accounts: Mapped[list["TelegramAccountModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    devices: Mapped[list["DeviceModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    projects: Mapped[list["ProjectModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


class TelegramAccountModel(Base):
    __tablename__ = "telegram_accounts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(80))
    first_name: Mapped[str | None] = mapped_column(String(120))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped["UserModel"] = relationship(back_populates="telegram_accounts")


class DeviceModel(Base):
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_devices_user_name"),
        Index("ix_devices_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    device_token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="registered")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    user: Mapped["UserModel"] = relationship(back_populates="devices")
    sessions: Mapped[list["WorkerSessionModel"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
    )
    agent_integrations: Mapped[list["AgentIntegrationModel"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
    )


class WorkerSessionModel(Base):
    __tablename__ = "worker_sessions"
    __table_args__ = (Index("ix_worker_sessions_device_status", "device_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="connected")
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    device: Mapped["DeviceModel"] = relationship(back_populates="sessions")


class ProjectModel(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_projects_user_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    root_path: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    user: Mapped["UserModel"] = relationship(back_populates="projects")
    role_assignments: Mapped[list["RoleAssignmentModel"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    tasks: Mapped[list["TaskModel"]] = relationship(back_populates="project")


class AgentIntegrationModel(Base):
    __tablename__ = "agent_integrations"
    __table_args__ = (
        UniqueConstraint("device_id", "agent_id", name="uq_agent_integrations_device_agent"),
        Index("ix_agent_integrations_device_ready", "device_id", "ready"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(String(80))
    display_name: Mapped[str] = mapped_column(String(120))
    provider: Mapped[str] = mapped_column(String(80))
    executable: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    installed: Mapped[bool] = mapped_column(Boolean, default=False)
    probe_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    ready: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(40), default="unknown")
    version: Mapped[str | None] = mapped_column(String(120))
    last_probe_status: Mapped[str | None] = mapped_column(String(40))
    last_probe_detail: Mapped[str | None] = mapped_column(Text)
    last_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    device: Mapped["DeviceModel"] = relationship(back_populates="agent_integrations")
    role_assignments: Mapped[list["RoleAssignmentModel"]] = relationship(
        back_populates="agent_integration",
    )


class RoleAssignmentModel(Base):
    __tablename__ = "role_assignments"
    __table_args__ = (UniqueConstraint("project_id", "role", name="uq_role_assignments_project_role"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(40))
    agent_integration_id: Mapped[str] = mapped_column(
        ForeignKey("agent_integrations.id", ondelete="RESTRICT"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    project: Mapped["ProjectModel"] = relationship(back_populates="role_assignments")
    agent_integration: Mapped["AgentIntegrationModel"] = relationship(
        back_populates="role_assignments",
    )


class TaskModel(Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_project_status", "project_id", "status"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), index=True)
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    request_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    project: Mapped["ProjectModel"] = relationship(back_populates="tasks")
    results: Mapped[list["TaskResultModel"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )


class TaskResultModel(Base):
    __tablename__ = "task_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(40))
    output: Mapped[str] = mapped_column(Text, default="")
    result_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    task: Mapped["TaskModel"] = relationship(back_populates="results")


class UserSessionModel(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_user_expires", "user_id", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    user_agent: Mapped[str | None] = mapped_column(String(120))


class UserAgentConfigModel(Base):
    """Per-user agent configuration — pengganti env var ENABLE_CODEX dst.

    Dipakai backend untuk routing intent ``agent_code/review/architect`` ke
    agent tertentu. Worker user TIDAK perlu cek enabled — backend yang putuskan
    apakah agent boleh dipanggil.
    """

    __tablename__ = "user_agent_configs"
    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", name="uq_user_agent_configs_user_agent"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    agent_id: Mapped[str] = mapped_column(String(40))  # codex, claude, glm, ...
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[str | None] = mapped_column(String(40))  # engineer, reviewer, architect, NULL
    model: Mapped[str | None] = mapped_column(String(120))  # override default model
    concurrency: Mapped[int] = mapped_column(default=1)  # max parallel jobs
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class ChatMessageModel(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[str] = mapped_column(String(80), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditEventModel(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_trace", "trace_id"),
        Index("ix_audit_events_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)
    trace_id: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(80))
    event_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
