from dataclasses import dataclass


@dataclass(frozen=True)
class TenantIdentity:
    user_id: str
    telegram_account_id: str
    telegram_user_id: int


@dataclass(frozen=True)
class DeviceIdentity:
    device_id: str
    user_id: str
    name: str
