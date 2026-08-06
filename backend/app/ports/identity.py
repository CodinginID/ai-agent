from typing import Protocol

from app.domain.accounts import TenantIdentity


class TenantResolverPort(Protocol):
    def resolve_by_telegram_user_id(self, telegram_user_id: int) -> TenantIdentity | None: ...
