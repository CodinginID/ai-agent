"""HTTP endpoint untuk roster pasukan — CRUD nama/peran agen gather-room.

Auth memakai model yang sama seperti ``/chat`` dan ``/push``: Bearer session
token, atau ``ADMIN_TOKEN`` + ``as_email`` (admin kelola roster user lain).

Setiap mutasi (PUT/DELETE) mem-publish ``roster.updated`` ke ``RoomBus``
supaya klien lain yang sedang membuka ``/room/stream`` ikut refresh tanpa
polling.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated

from fastapi import APIRouter, Body, Header, HTTPException, status
from pydantic import BaseModel

from app.composition import build_roster
from app.interfaces.chat import _resolve_user_and_conv
from app.ports.roster import ROSTER_ROLES, RosterAgent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/room/roster", tags=["roster"])

# Sama seperti id agen default (huruf kecil, angka, dash) — dipakai juga untuk
# id hasil slugifikasi nama di frontend.
_ID_RE = re.compile(r"^[a-z0-9-]{1,32}$")


def _agent_dict(agent: RosterAgent) -> dict[str, str]:
    return {"id": agent.id, "name": agent.name, "role": agent.role}


def _publish_roster_updated(agents: list[RosterAgent]) -> None:
    """Best-effort — kegagalan publish tak boleh menggagalkan mutasi CRUD."""
    try:
        from app.interfaces.room import publish_room_event

        publish_room_event("roster.updated", agents=[_agent_dict(a) for a in agents])
    except Exception:
        logger.debug("roster publish gagal", exc_info=True)


class RosterUpsertRequest(BaseModel):
    name: str
    role: str
    as_email: str | None = None


@router.get("")
async def roster_list(
    authorization: str | None = Header(default=None),
    as_email: str | None = None,
) -> list[dict[str, str]]:
    user_id, _conv_id = _resolve_user_and_conv(authorization, as_email)
    agents = await build_roster().list(user_id)
    return [_agent_dict(a) for a in agents]


@router.put("/{agent_id}")
async def roster_upsert(
    agent_id: str,
    req: Annotated[RosterUpsertRequest, Body(...)],
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    user_id, _conv_id = _resolve_user_and_conv(authorization, req.as_email)

    if not _ID_RE.match(agent_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="id agen tidak valid (a-z, 0-9, dash; maks 32 karakter)",
        )
    name = req.name.strip()
    if not (1 <= len(name) <= 24):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="nama harus 1-24 karakter",
        )
    if req.role not in ROSTER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"peran tidak dikenal: {req.role}",
        )

    store = build_roster()
    agent = RosterAgent(id=agent_id, name=name, role=req.role)
    await store.upsert(user_id, agent)
    _publish_roster_updated(await store.list(user_id))
    return _agent_dict(agent)


@router.delete("/{agent_id}")
async def roster_delete(
    agent_id: str,
    authorization: str | None = Header(default=None),
    as_email: str | None = None,
) -> dict[str, bool]:
    user_id, _conv_id = _resolve_user_and_conv(authorization, as_email)

    store = build_roster()
    agents = await store.list(user_id)
    target = next((a for a in agents if a.id == agent_id), None)
    if target is not None and target.role == "manager":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="manajer tidak bisa dihapus — harus ada tepat satu manajer",
        )

    ok = await store.delete(user_id, agent_id)
    if ok:
        _publish_roster_updated(await store.list(user_id))
    return {"ok": ok}
