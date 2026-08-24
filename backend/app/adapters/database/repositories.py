from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.database.models import (
    AgentIntegrationModel,
    DeviceModel,
    ProjectModel,
    SkillModel,
    TelegramAccountModel,
    UserModel,
    utc_now,
)
from app.domain.accounts import DeviceIdentity, TenantIdentity
from app.domain.skills import Skill, parse_skill, skill_to_dict


class DatabaseConflictError(Exception):
    pass


class ControlPlaneRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_user(self, display_name: str | None = None, email: str | None = None) -> UserModel:
        user = UserModel(display_name=display_name, email=email)
        self._session.add(user)
        self._session.flush()
        return user

    def get_user_by_email(self, email: str) -> UserModel | None:
        return self._session.scalar(
            select(UserModel).where(UserModel.email == email)
        )

    def link_telegram_account(
        self,
        user_id: str,
        telegram_user_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ) -> TelegramAccountModel:
        existing = self._session.scalar(
            select(TelegramAccountModel).where(
                TelegramAccountModel.telegram_user_id == telegram_user_id,
            )
        )
        if existing is not None:
            raise DatabaseConflictError("Telegram account is already linked")

        account = TelegramAccountModel(
            user_id=user_id,
            telegram_user_id=telegram_user_id,
            username=username,
            first_name=first_name,
        )
        self._session.add(account)
        self._session.flush()
        return account

    def resolve_by_telegram_user_id(self, telegram_user_id: int) -> TenantIdentity | None:
        account = self._session.scalar(
            select(TelegramAccountModel).where(
                TelegramAccountModel.telegram_user_id == telegram_user_id,
            )
        )
        if account is None:
            return None

        return TenantIdentity(
            user_id=account.user_id,
            telegram_account_id=account.id,
            telegram_user_id=account.telegram_user_id,
        )

    def register_device(
        self,
        user_id: str,
        name: str,
        device_token_hash: str,
    ) -> DeviceIdentity:
        existing = self._session.scalar(
            select(DeviceModel).where(
                DeviceModel.user_id == user_id,
                DeviceModel.name == name,
            )
        )
        if existing is not None:
            raise DatabaseConflictError("Device name is already registered for this user")

        device = DeviceModel(
            user_id=user_id,
            name=name,
            device_token_hash=device_token_hash,
        )
        self._session.add(device)
        self._session.flush()
        return DeviceIdentity(device_id=device.id, user_id=device.user_id, name=device.name)

    def create_project(
        self,
        user_id: str,
        name: str,
        root_path: str,
        description: str = "",
    ) -> ProjectModel:
        existing = self._session.scalar(
            select(ProjectModel).where(
                ProjectModel.user_id == user_id,
                ProjectModel.name == name,
            )
        )
        if existing is not None:
            raise DatabaseConflictError("Project name is already registered for this user")

        project = ProjectModel(
            user_id=user_id,
            name=name,
            root_path=root_path,
            description=description,
        )
        self._session.add(project)
        self._session.flush()
        return project

    def find_or_create_device_by_name(self, user_id: str, name: str) -> DeviceModel:
        """Find existing device by (user_id, name) or create one for WS auto-registration."""
        import hashlib

        existing = self._session.scalar(
            select(DeviceModel).where(
                DeviceModel.user_id == user_id,
                DeviceModel.name == name,
            )
        )
        if existing is not None:
            return existing
        token_hash = hashlib.sha256(f"ws:{user_id}:{name}".encode()).hexdigest()[:64]
        device = DeviceModel(user_id=user_id, name=name, device_token_hash=token_hash)
        self._session.add(device)
        self._session.flush()
        return device

    def list_devices(self, user_id: str) -> list[DeviceModel]:
        return list(self._session.scalars(
            select(DeviceModel).where(DeviceModel.user_id == user_id)
        ))

    def get_device(self, device_id: str, user_id: str) -> DeviceModel | None:
        return self._session.scalar(
            select(DeviceModel).where(
                DeviceModel.id == device_id,
                DeviceModel.user_id == user_id,
            )
        )

    # ── Project / active-project helpers ─────────────────────────────────────

    def list_user_projects(self, user_id: str) -> list[ProjectModel]:
        return list(self._session.scalars(
            select(ProjectModel).where(ProjectModel.user_id == user_id)
        ))

    def get_project(self, project_id: str, user_id: str) -> ProjectModel | None:
        return self._session.scalar(
            select(ProjectModel).where(
                ProjectModel.id == project_id,
                ProjectModel.user_id == user_id,
            )
        )

    def get_or_create_default_project(self, user_id: str) -> ProjectModel:
        """Ensure user punya minimal satu project. Idempotent.

        Default project bertindak sebagai fallback untuk user yang belum eksplisit
        bikin project — jadi scratchpad/RAG punya scope yang valid sejak request
        pertama.
        """
        existing = self._session.scalar(
            select(ProjectModel)
            .where(ProjectModel.user_id == user_id)
            .order_by(ProjectModel.created_at)
            .limit(1)
        )
        if existing is not None:
            return existing
        project = ProjectModel(
            user_id=user_id,
            name="default",
            root_path=".",
            description="Auto-created default project",
        )
        self._session.add(project)
        self._session.flush()
        return project

    def set_device_active_project(
        self, device_id: str, user_id: str, project_id: str
    ) -> DeviceModel:
        """Switch device's active project. Validate project ownership.

        Raise ``DatabaseConflictError`` kalau device tidak ada atau project bukan
        milik user yang sama.
        """
        device = self.get_device(device_id, user_id)
        if device is None:
            raise DatabaseConflictError(f"Device {device_id} tidak ditemukan untuk user")
        project = self.get_project(project_id, user_id)
        if project is None:
            raise DatabaseConflictError(f"Project {project_id} tidak ditemukan untuk user")
        device.active_project_id = project.id
        self._session.flush()
        return device

    def resolve_device_project_id(self, device_id: str, user_id: str) -> str | None:
        """Return active_project_id atau None kalau belum di-set / device tidak ada."""
        device = self.get_device(device_id, user_id)
        return device.active_project_id if device else None

    def list_agent_integrations(self, device_id: str) -> list[AgentIntegrationModel]:
        return list(self._session.scalars(
            select(AgentIntegrationModel).where(
                AgentIntegrationModel.device_id == device_id
            )
        ))

    def upsert_agent_integration(
        self,
        device_id: str,
        agent_id: str,
        display_name: str,
        provider: str,
        executable: str | None,
        installed: bool,
        enabled: bool,
        probe_ok: bool,
        status: str,
        version: str | None = None,
        probe_detail: str | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> AgentIntegrationModel:
        integration = self._session.scalar(
            select(AgentIntegrationModel).where(
                AgentIntegrationModel.device_id == device_id,
                AgentIntegrationModel.agent_id == agent_id,
            )
        )
        ready = installed and enabled and probe_ok
        now = utc_now()

        if integration is None:
            integration = AgentIntegrationModel(
                device_id=device_id,
                agent_id=agent_id,
                display_name=display_name,
                provider=provider,
                executable=executable,
            )
            self._session.add(integration)

        integration.display_name = display_name
        integration.provider = provider
        integration.executable = executable
        integration.installed = installed
        integration.enabled = enabled
        integration.probe_ok = probe_ok
        integration.ready = ready
        integration.status = status
        integration.version = version
        integration.last_probe_status = "ok" if probe_ok else "failed"
        integration.last_probe_detail = probe_detail
        integration.last_probe_at = now
        integration.capabilities = capabilities or {}
        self._session.flush()
        return integration

    # ── Skills ────────────────────────────────────────────────────────────────

    def create_skill(
        self, project_id: str, user_id: str, definition: dict[str, Any]
    ) -> SkillModel:
        """Validate JSON definition + persist. Raise ``DatabaseConflictError``
        kalau project bukan milik user atau skill name sudah ada.
        Raise ``SkillValidationError`` kalau JSON tidak valid.
        """
        project = self.get_project(project_id, user_id)
        if project is None:
            raise DatabaseConflictError(
                f"Project {project_id} tidak ditemukan untuk user"
            )
        skill = parse_skill(definition)
        existing = self._session.scalar(
            select(SkillModel).where(
                SkillModel.project_id == project_id,
                SkillModel.name == skill.name,
            )
        )
        if existing is not None:
            raise DatabaseConflictError(
                f"Skill '{skill.name}' sudah ada di project ini"
            )
        row = SkillModel(
            project_id=project_id,
            name=skill.name,
            description=skill.description,
            definition=skill_to_dict(skill),
        )
        self._session.add(row)
        self._session.flush()
        return row

    def list_project_skills(self, project_id: str, user_id: str) -> list[SkillModel]:
        if self.get_project(project_id, user_id) is None:
            return []
        return list(self._session.scalars(
            select(SkillModel).where(SkillModel.project_id == project_id)
        ))

    def get_skill(
        self, skill_id: str, user_id: str
    ) -> SkillModel | None:
        """Fetch skill, scoped by user (via project ownership)."""
        row = self._session.scalar(
            select(SkillModel)
            .join(ProjectModel, SkillModel.project_id == ProjectModel.id)
            .where(SkillModel.id == skill_id, ProjectModel.user_id == user_id)
        )
        return row

    def get_skill_by_name(
        self, project_id: str, name: str, user_id: str
    ) -> SkillModel | None:
        if self.get_project(project_id, user_id) is None:
            return None
        return self._session.scalar(
            select(SkillModel).where(
                SkillModel.project_id == project_id,
                SkillModel.name == name,
            )
        )

    def update_skill(
        self, skill_id: str, user_id: str, definition: dict[str, Any]
    ) -> SkillModel:
        row = self.get_skill(skill_id, user_id)
        if row is None:
            raise DatabaseConflictError(f"Skill {skill_id} tidak ditemukan")
        skill = parse_skill(definition)
        # Rename collision check kalau name berubah
        if skill.name != row.name:
            clash = self._session.scalar(
                select(SkillModel).where(
                    SkillModel.project_id == row.project_id,
                    SkillModel.name == skill.name,
                    SkillModel.id != row.id,
                )
            )
            if clash is not None:
                raise DatabaseConflictError(
                    f"Skill '{skill.name}' sudah dipakai di project ini"
                )
        row.name = skill.name
        row.description = skill.description
        row.definition = skill_to_dict(skill)
        self._session.flush()
        return row

    def delete_skill(self, skill_id: str, user_id: str) -> bool:
        row = self.get_skill(skill_id, user_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True

    def load_skill_domain(self, row: SkillModel) -> Skill:
        """Helper untuk caller yang butuh ``Skill`` dataclass (mis. executor)."""
        return parse_skill(row.definition)
