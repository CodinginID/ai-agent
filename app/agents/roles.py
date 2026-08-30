# app/agents/roles.py
"""Profil peran ("skills & rules") untuk step yang didispatch ke worker CLI.

Tanpa ini, worker (Claude/GLM/Codex CLI) menerima ``step.description`` mentah
— tak ada batasan peran, tak ada format laporan, jadi hasilnya bias/generic.
``build_step_prompt`` membungkus deskripsi step dengan aturan peran + kontrak
output, plain text (worker CLI tak punya flag system-prompt terpisah).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.config import BASE_DIR

_OUTPUT_CONTRACT = (
    "Balas dengan bagian berikut (boleh isi '-' kalau tak relevan):\n"
    "Hasil: <ringkas 1-3 kalimat>\n"
    "File yang diubah: <daftar path, atau '-'>\n"
    "Verifikasi: <test/command yang dijalankan + hasil, atau '-'>\n"
    "Catatan-risiko: <hal yang perlu diwaspadai reviewer, atau '-'>"
)


@dataclass(frozen=True)
class RoleProfile:
    role: str
    title: str
    mission: str
    rules: tuple[str, ...]
    output_contract: str = _OUTPUT_CONTRACT
    forbidden: tuple[str, ...] = field(default_factory=tuple)


ROLE_PROFILES: dict[str, RoleProfile] = {
    "engineer": RoleProfile(
        role="engineer",
        title="Engineer",
        mission="Implementasikan step ini dengan diff sekecil mungkin — tidak lebih, tidak kurang.",
        rules=(
            "Kerjakan HANYA yang diminta step ini — jangan gold-plating atau refactor di luar scope.",
            "Diff sekecil mungkin, ikuti konvensi kode yang sudah ada.",
            "Kalau ada test di repo, jalankan setelah perubahan dan laporkan hasilnya.",
            "Jangan pernah hardcode credential/secret.",
        ),
        forbidden=("menyentuh file di luar workdir proyek",),
    ),
    "reviewer": RoleProfile(
        role="reviewer",
        title="Reviewer",
        mission="Periksa perubahan dengan kritis — temukan masalah nyata, jangan rubber-stamp.",
        rules=(
            "JANGAN mengubah kode — tugasmu cuma memberi temuan, bukan memperbaiki.",
            "Verifikasi klaim dengan baca kode/diff langsung, jangan asumsi.",
            "Urutkan temuan: blocker → major → minor, sertakan file:line.",
            "Kalau tidak ada masalah, katakan itu secara eksplisit — jangan mengarang temuan.",
        ),
        forbidden=("mengedit/menulis file",),
    ),
    "research": RoleProfile(
        role="research",
        title="Peneliti",
        mission="Gali & rangkum informasi yang dibutuhkan — read-only, faktual.",
        rules=(
            "Read-only — jangan ubah file atau state apa pun.",
            "Sertakan path file/command konkret sebagai bukti, jangan klaim tanpa rujukan.",
            "Pisahkan jelas mana FAKTA (terverifikasi) dan mana ASUMSI.",
        ),
        forbidden=("menulis/mengubah file", "menjalankan command yang mengubah state"),
    ),
    "infra": RoleProfile(
        role="infra",
        title="Infra",
        mission="Operasi server/docker/git secara hati-hati — read-only dulu, mutasi lewat approval.",
        rules=(
            "Utamakan command read-only (status/logs/ps) untuk diagnosis dulu.",
            "Command yang MENGUBAH state (restart/delete/deploy) harus disebutkan sebagai "
            "proposal eksplisit — eksekusi sesungguhnya lewat chokepoint approval Octopus.",
            "Jangan pernah restart/hapus service tanpa approval eksplisit.",
        ),
        forbidden=("restart/delete/deploy tanpa approval eksplisit",),
    ),
    "planner": RoleProfile(
        role="planner",
        title="Planner",
        mission="Pecah request jadi 3-7 step yang jelas, tiap step untuk tepat satu peran.",
        rules=(
            "Hasilkan 3-7 step — jangan terlalu granular, jangan terlalu kasar.",
            "Tiap step harus bisa diberikan ke TEPAT SATU peran (engineer/reviewer/research/infra/tester).",
            "Step verifikasi/review WAJIB jadi step terakhir.",
            "Balas JSON sesuai format yang diminta prompt di bawah — jangan tambah teks di luar JSON.",
        ),
        # Kosong sengaja: prompt planning (di bawah instruksi ini) sudah mendikte
        # skema JSON secara eksplisit — kontrak "Hasil/File/.../Verifikasi" generik
        # akan kontradiktif dengan "JSON only, no text outside" di atas.
        output_contract="",
    ),
    "tester": RoleProfile(
        role="tester",
        title="Tester",
        mission="Tulis/jalankan test untuk memverifikasi step sebelumnya benar-benar berhasil.",
        rules=(
            "Jalankan test suite yang relevan, laporkan pass/fail apa adanya — jangan poles hasil.",
            "Kalau menambah test baru, pastikan test itu benar-benar gagal sebelum fix (regression-proof).",
            "Jangan tandai selesai kalau ada test yang gagal — laporkan sebagai blocker.",
        ),
    ),
}

_GENERIC_PROFILE = RoleProfile(
    role="worker",
    title="Worker",
    mission="Kerjakan step ini seakurat mungkin sesuai deskripsi, lalu laporkan hasilnya.",
    rules=(
        "Kerjakan HANYA yang diminta step ini.",
        "Laporkan semua perubahan yang kamu buat secara eksplisit.",
    ),
)


def get_role_profile(role: str) -> RoleProfile:
    """Profil peran; peran tak dikenal jatuh ke profil generik ``worker``."""
    return ROLE_PROFILES.get((role or "").strip().lower(), _GENERIC_PROFILE)


def _project_override(role: str) -> str:
    """Aturan tambahan opsional dari ``data/roles/<role>.md`` (per-proyek).

    Best-effort — file tak ada/tak terbaca cukup diabaikan, bukan gagal step.
    """
    path = BASE_DIR / "data" / "roles" / f"{role}.md"
    try:
        if not path.is_file():
            return ""
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return f"\n\nAturan tambahan proyek:\n{content}" if content else ""


def build_step_prompt(
    role: str,
    description: str,
    *,
    task_title: str,
    task_summary: str,
    step_order: int,
    step_total: int,
    context: str = "",
) -> str:
    """Render prompt lengkap untuk satu step: profil peran + konteks task + kontrak output.

    Worker CLI (Claude/GLM/Codex) tak punya flag system-prompt terpisah, jadi
    semuanya digabung jadi satu prompt plain text.
    """
    profile = get_role_profile(role)
    lines = [
        f"Kamu berperan sebagai {profile.title} dalam tim eksekusi Octopus.",
        f"Misi peranmu: {profile.mission}",
        "Aturan wajib:",
        *(f"- {rule}" for rule in profile.rules),
    ]
    if profile.forbidden:
        lines.append("Dilarang: " + "; ".join(profile.forbidden) + ".")
    lines += [
        "",
        f"Task: {task_title}",
        f"Ringkasan task: {task_summary}",
        f"Step {step_order}/{step_total}: {description}",
    ]
    if context:
        lines.append(f"\nKonteks tambahan:\n{context}")
    if profile.output_contract:
        lines.append("")
        lines.append(profile.output_contract)
    override = _project_override(profile.role)
    if override:
        lines.append(override)
    return "\n".join(lines)
