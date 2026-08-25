"""Command policy — ALLOW-LIST model.

Agen boleh menjalankan perintah READ-ONLY / diagnostik secara bebas lewat
``run_safe``. Perintah yang mengubah sistem, mengirim data keluar, atau tidak
dikenal → DITOLAK di sini; aksi semacam itu harus lewat action ber-approval
(human-in-the-loop), bukan command shell mentah hasil generate LLM.

Ini kebalikan dari deny-list lama yang bolong (``rm -r``, ``systemctl stop``,
``docker rm -f``, ``git push --force``, pipe-to-shell, dll. semuanya lolos):
allow-list tidak bisa "kebobolan" oleh perintah destruktif yang tak terduga —
apa pun yang tidak eksplisit aman, ditolak.
"""

from __future__ import annotations

# Executable read-only murni — argumen apa pun aman (tidak mengubah state).
_ALWAYS_SAFE: frozenset[str] = frozenset({
    # inspeksi file/teks
    "ls", "cat", "head", "tail", "grep", "egrep", "fgrep", "rg", "find", "fd",
    "stat", "file", "wc", "sort", "uniq", "cut", "tr", "column", "nl", "tac",
    "readlink", "realpath", "basename", "dirname", "tree", "diff",
    # info sistem
    "df", "du", "free", "uptime", "whoami", "pwd", "hostname", "ps", "date",
    "uname", "env", "printenv", "which", "type", "id", "w", "who", "nproc",
    "lscpu", "lsblk", "lsmod", "vmstat", "iostat", "dmesg",
    "echo", "true", "false", "seq",
    # info jaringan (tanpa kirim data)
    "ss", "netstat", "ip", "dig", "nslookup", "host",
    # log viewer (read-only)
    "journalctl",
    "fastfetch", "neofetch",
})

# Executable dual-use — hanya subcommand read-only yang diizinkan.
_SUBCOMMAND_SAFE: dict[str, frozenset[str]] = {
    "docker": frozenset({
        "ps", "images", "logs", "stats", "inspect", "version", "info",
        "top", "port", "diff", "history",
    }),
    "git": frozenset({
        "status", "log", "diff", "show", "branch", "remote", "describe",
        "rev-parse", "blame", "shortlog", "ls-files", "cat-file", "tag",
    }),
    "systemctl": frozenset({
        "status", "is-active", "is-enabled", "is-failed",
        "list-units", "list-unit-files", "show", "cat",
    }),
    "kubectl": frozenset({"get", "describe", "logs", "top", "version", "explain"}),
    "npm": frozenset({"ls", "list", "outdated", "view", "config"}),
    "pip": frozenset({"list", "show", "freeze"}),
}

# docker compose <sub> — subcommand read-only.
_DOCKER_COMPOSE_SAFE: frozenset[str] = frozenset(
    {"ps", "config", "logs", "top", "images", "version"}
)


def validate_args(args: list[str]) -> tuple[bool, str]:
    """Return ``(allowed, reason)``; ``reason`` kosong saat diizinkan.

    Allow-list: hanya executable/subcommand read-only yang lolos. Sisanya
    ditolak dengan pesan yang mengarahkan ke jalur approval.
    """
    if not args:
        return False, "Command kosong"

    executable = args[0].strip().split("/")[-1]

    if executable in _ALWAYS_SAFE:
        return True, ""

    if executable in _SUBCOMMAND_SAFE:
        sub = args[1].strip() if len(args) > 1 else ""
        if executable == "docker" and sub == "compose":
            csub = args[2].strip() if len(args) > 2 else ""
            if csub in _DOCKER_COMPOSE_SAFE:
                return True, ""
            return False, (
                f"'docker compose {csub or '?'}' bukan read-only — butuh persetujuan"
            )
        if sub in _SUBCOMMAND_SAFE[executable]:
            return True, ""
        return False, (
            f"'{executable} {sub or '?'}' bukan subcommand read-only — "
            "aksi yang mengubah sistem harus lewat approval"
        )

    return False, (
        f"Executable '{executable}' tidak ada di allow-list read-only — "
        "perintah yang mengubah sistem/jaringan harus lewat approval, "
        "bukan command mentah dari LLM"
    )
