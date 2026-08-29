"""Port untuk roster pasukan (CRUD nama/peran agen) — mengendalikan siapa yang
tampil di gather-room, terpisah dari presence worker (``worker_registry``).

Konsep sama seperti port lain (push, github_issues): domain/interfaces
tergantung pada Protocol ini, bukan implementasi konkret (``RedisRosterStore``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# Peran yang boleh dipakai roster — selaras dengan Role di frontend (types.ts).
ROSTER_ROLES = frozenset(
    {"manager", "coder", "tester", "reviewer", "deployer", "researcher"}
)


@dataclass(frozen=True)
class RosterAgent:
    """Satu baris roster: identitas agen yang tampil di gather-room."""

    id: str
    name: str
    role: str


# Cast tetap ruangan (selaras mockup) — dipindah dari app/interfaces/room.py
# supaya jadi satu sumber kebenaran yang dipakai baik fallback maupun seed
# awal RedisRosterStore.
DEFAULT_ROSTER: tuple[RosterAgent, ...] = (
    RosterAgent(id="octo", name="Octo", role="manager"),
    RosterAgent(id="nadia", name="Nadia", role="coder"),
    RosterAgent(id="bima", name="Bima", role="coder"),
    RosterAgent(id="sari", name="Sari", role="tester"),
    RosterAgent(id="rangga", name="Rangga", role="reviewer"),
    RosterAgent(id="dewi", name="Dewi", role="deployer"),
    RosterAgent(id="yusuf", name="Yusuf", role="researcher"),
)


class RosterPort(Protocol):
    async def list(self, user_id: str) -> list[RosterAgent]: ...

    async def upsert(self, user_id: str, agent: RosterAgent) -> None: ...

    async def delete(self, user_id: str, agent_id: str) -> bool:
        """Return True kalau agent memang ada & terhapus."""
        ...
