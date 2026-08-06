"""Skill DSL — workflow deklaratif user-defined untuk multi-agent orkestrasi.

Skill adalah graf DAG dari steps. Setiap step di-execute oleh agent yang
assigned ke ``role`` step tersebut (lihat ``app.adapters.agent_configs``).
``depends_on`` menentukan urutan + memungkinkan hand-off output antar step.

Format JSON contoh::

    {
      "name": "build-company-profile-site",
      "description": "Bikin website company profile end-to-end.",
      "steps": [
        {"name": "design",     "role": "architect", "depends_on": []},
        {"name": "copy",       "role": "engineer",  "depends_on": ["design"]},
        {"name": "code",       "role": "engineer",  "depends_on": ["design", "copy"]},
        {"name": "review",     "role": "reviewer",  "depends_on": ["code"]}
      ],
      "manager": {
        "role": "architect",
        "max_revisions": 2,
        "acceptance_criteria": "All outputs combined satisfy the brief"
      }
    }

Pure domain — zero import library eksternal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.capabilities import ROLE_REQUIRED_CAPABILITIES

# ── Errors ────────────────────────────────────────────────────────────────────


class SkillValidationError(ValueError):
    """JSON Skill tidak valid — DAG cycle, unknown role, atau format salah."""


# ── Entities ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Step:
    name: str
    role: str
    depends_on: tuple[str, ...] = ()
    prompt_template: str | None = None
    produces: str | None = None


@dataclass(frozen=True)
class Manager:
    """Phase-2 manager config. Phase-1 executor abaikan field ini."""

    role: str
    max_revisions: int = 2
    acceptance_criteria: str = ""


@dataclass(frozen=True)
class Skill:
    name: str
    steps: tuple[Step, ...]
    description: str = ""
    manager: Manager | None = None


# ── Constants ─────────────────────────────────────────────────────────────────

MAX_STEPS = 50
MAX_NAME_LEN = 120
MAX_DESCRIPTION_LEN = 2000

# Sengaja loose — biar user bisa nama step apapun selama tidak kosong.
_FORBIDDEN_CHARS = set("/\\\t\n\r")


# ── Validation primitives ─────────────────────────────────────────────────────


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise SkillValidationError(f"{field_name} harus string, dapat {type(value).__name__}")
    return value


def _require_non_empty(value: str, field_name: str) -> str:
    if not value.strip():
        raise SkillValidationError(f"{field_name} tidak boleh kosong")
    return value


def _validate_name(value: str, field_name: str) -> str:
    _require_non_empty(value, field_name)
    if len(value) > MAX_NAME_LEN:
        raise SkillValidationError(
            f"{field_name} terlalu panjang (max {MAX_NAME_LEN} char)"
        )
    if _FORBIDDEN_CHARS & set(value):
        raise SkillValidationError(f"{field_name} mengandung char terlarang")
    return value


def _validate_role(role: str, context: str) -> str:
    _require_non_empty(role, f"role di {context}")
    if role not in ROLE_REQUIRED_CAPABILITIES:
        known = ", ".join(sorted(ROLE_REQUIRED_CAPABILITIES))
        raise SkillValidationError(
            f"Role '{role}' di {context} tidak dikenal. Pilih: {known}"
        )
    return role


def _detect_cycle(steps: list[Step]) -> None:
    """Topological sort dengan Kahn algorithm — kalau gagal, ada cycle."""
    indeg: dict[str, int] = {s.name: 0 for s in steps}
    graph: dict[str, list[str]] = {s.name: [] for s in steps}
    for s in steps:
        for dep in s.depends_on:
            graph[dep].append(s.name)
            indeg[s.name] += 1
    queue = [n for n, d in indeg.items() if d == 0]
    visited = 0
    while queue:
        n = queue.pop()
        visited += 1
        for child in graph[n]:
            indeg[child] -= 1
            if indeg[child] == 0:
                queue.append(child)
    if visited != len(steps):
        raise SkillValidationError(
            "Cycle terdeteksi di steps.depends_on — workflow tidak boleh recursive"
        )


# ── Parser ────────────────────────────────────────────────────────────────────


def parse_step(data: Any, index: int) -> Step:
    if not isinstance(data, dict):
        raise SkillValidationError(f"steps[{index}] harus object, dapat {type(data).__name__}")

    raw_name = data.get("name") or data.get("role")  # role boleh dipakai sebagai default name
    name = _validate_name(_require_str(raw_name, f"steps[{index}].name"), f"steps[{index}].name")
    role = _validate_role(_require_str(data.get("role"), f"steps[{index}].role"), f"steps[{index}]")

    raw_deps = data.get("depends_on", [])
    if not isinstance(raw_deps, list):
        raise SkillValidationError(f"steps[{index}].depends_on harus list")
    deps: list[str] = []
    for d in raw_deps:
        deps.append(_validate_name(_require_str(d, f"steps[{index}].depends_on item"), "depends_on"))

    prompt_tpl = data.get("prompt_template")
    if prompt_tpl is not None and not isinstance(prompt_tpl, str):
        raise SkillValidationError(f"steps[{index}].prompt_template harus string atau null")

    produces = data.get("produces")
    if produces is not None:
        produces = _validate_name(_require_str(produces, "produces"), "produces")

    return Step(
        name=name,
        role=role,
        depends_on=tuple(deps),
        prompt_template=prompt_tpl,
        produces=produces,
    )


def parse_manager(data: Any) -> Manager:
    if not isinstance(data, dict):
        raise SkillValidationError(f"manager harus object, dapat {type(data).__name__}")
    role = _validate_role(_require_str(data.get("role"), "manager.role"), "manager")
    max_rev = data.get("max_revisions", 2)
    if not isinstance(max_rev, int) or max_rev < 0:
        raise SkillValidationError("manager.max_revisions harus integer ≥ 0")
    crit = data.get("acceptance_criteria", "")
    if not isinstance(crit, str):
        raise SkillValidationError("manager.acceptance_criteria harus string")
    return Manager(role=role, max_revisions=max_rev, acceptance_criteria=crit)


def parse_skill(data: Any) -> Skill:
    """Validate + load Skill dari dict (mis. hasil json.loads).

    Raise ``SkillValidationError`` dengan pesan deskriptif kalau format salah.
    """
    if not isinstance(data, dict):
        raise SkillValidationError(f"skill harus object, dapat {type(data).__name__}")

    name = _validate_name(_require_str(data.get("name"), "name"), "name")

    description = data.get("description", "")
    if not isinstance(description, str):
        raise SkillValidationError("description harus string")
    if len(description) > MAX_DESCRIPTION_LEN:
        raise SkillValidationError(
            f"description terlalu panjang (max {MAX_DESCRIPTION_LEN} char)"
        )

    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise SkillValidationError("steps harus list non-kosong")
    if len(raw_steps) > MAX_STEPS:
        raise SkillValidationError(f"jumlah steps melebihi cap ({MAX_STEPS})")

    steps = [parse_step(s, i) for i, s in enumerate(raw_steps)]

    # Step name unik
    seen: set[str] = set()
    for s in steps:
        if s.name in seen:
            raise SkillValidationError(f"step name '{s.name}' duplikat")
        seen.add(s.name)

    # depends_on harus reference step yang ada
    for s in steps:
        for dep in s.depends_on:
            if dep not in seen:
                raise SkillValidationError(
                    f"step '{s.name}' depends_on '{dep}' yang tidak terdaftar"
                )
            if dep == s.name:
                raise SkillValidationError(f"step '{s.name}' depends_on dirinya sendiri")

    _detect_cycle(steps)

    raw_manager = data.get("manager")
    manager = parse_manager(raw_manager) if raw_manager is not None else None

    return Skill(
        name=name,
        description=description,
        steps=tuple(steps),
        manager=manager,
    )


# ── Serialization (round-trip with parse_skill) ───────────────────────────────


def skill_to_dict(skill: Skill) -> dict[str, Any]:
    """Inverse dari ``parse_skill`` — supaya bisa store-then-load round-trip."""
    out: dict[str, Any] = {
        "name": skill.name,
        "description": skill.description,
        "steps": [
            {
                "name": s.name,
                "role": s.role,
                "depends_on": list(s.depends_on),
                **({"prompt_template": s.prompt_template} if s.prompt_template else {}),
                **({"produces": s.produces} if s.produces else {}),
            }
            for s in skill.steps
        ],
    }
    if skill.manager is not None:
        out["manager"] = {
            "role": skill.manager.role,
            "max_revisions": skill.manager.max_revisions,
            "acceptance_criteria": skill.manager.acceptance_criteria,
        }
    return out


# ── DAG ordering (executor butuh ini di PR berikutnya) ────────────────────────


def topological_order(skill: Skill) -> list[Step]:
    """Return urutan step yang valid untuk eksekusi sequential.

    Stable: kalau dua step bisa dijalankan paralel, urutan-nya mengikuti
    urutan deklarasi user — bukan diacak. Bermanfaat untuk reproducibility.
    """
    by_name = {s.name: s for s in skill.steps}
    indeg = {s.name: len(s.depends_on) for s in skill.steps}
    ready: list[str] = [s.name for s in skill.steps if indeg[s.name] == 0]
    out: list[Step] = []

    graph: dict[str, list[str]] = {s.name: [] for s in skill.steps}
    for s in skill.steps:
        for dep in s.depends_on:
            graph[dep].append(s.name)

    declared_order = [s.name for s in skill.steps]
    while ready:
        # Pop earliest-declared ready step (stability).
        ready.sort(key=lambda n: declared_order.index(n))
        n = ready.pop(0)
        out.append(by_name[n])
        for child in graph[n]:
            indeg[child] -= 1
            if indeg[child] == 0:
                ready.append(child)

    if len(out) != len(skill.steps):
        # Defensive — seharusnya tidak terjadi karena parse_skill sudah cek cycle.
        raise SkillValidationError("Internal: topological sort tidak lengkap (cycle?)")
    return out


# ── Field for "extra context" — defaults ──────────────────────────────────────

_DEFAULT_TEMPLATE_VARS = {"prompt", "handoff", "recall"}  # placeholder for executor PR
_ = field  # keep import alive for downstream dataclass extensions
