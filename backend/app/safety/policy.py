from __future__ import annotations

import re

_DENIED_EXECUTABLES: frozenset[str] = frozenset({
    "mkfs", "mkfs.ext4", "mkfs.xfs", "fdisk", "parted", "gdisk",
    "dd", "shred", "wipe",
    "shutdown", "reboot", "halt", "poweroff", "init", "telinit",
    "passwd", "visudo",
})

# Pola berbahaya dalam full command string
_DENIED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brm\b.*-[a-zA-Z]*[rR][a-zA-Z]*[fF]"),   # rm -rf / rm -fr
    re.compile(r":\(\)\s*\{"),                               # fork bomb  :(){
    re.compile(r"\|\s*bash"),                                # pipe to bash
    re.compile(r"\|\s*sh\b"),                                # pipe to sh
    re.compile(r">\s*/etc/"),
    re.compile(r">\s*/bin/"),
    re.compile(r">\s*/sbin/"),
    re.compile(r">\s*/usr/"),
    re.compile(r">\s*/var/lib/"),
    re.compile(r">\s*/boot/"),
    re.compile(r">\s*/sys/"),
    re.compile(r">\s*/proc/"),
    re.compile(r"\bchmod\b.*-[a-zA-Z]*[rR]"),               # chmod -R
    re.compile(r"\bchown\b.*-[a-zA-Z]*[rR]"),               # chown -R
    re.compile(r"\bmv\b.+\s+/etc/"),
    re.compile(r"\bmv\b.+\s+/bin/"),
    re.compile(r"\bmv\b.+\s+/usr/"),
    re.compile(r"\beval\b"),
    re.compile(r"\bexec\b\s+\d*<"),                          # exec fd redirects
)


def validate_args(args: list[str]) -> tuple[bool, str]:
    """
    Returns (allowed, reason). reason is empty string when allowed.
    Validates against denied executables and dangerous command patterns.
    """
    if not args:
        return False, "Command kosong"

    executable = args[0].strip()

    # Strip path prefix  (/usr/bin/rm → rm)
    executable_base = executable.split("/")[-1]
    if executable_base in _DENIED_EXECUTABLES:
        return False, f"Executable '{executable_base}' tidak diizinkan"

    full_cmd = " ".join(args)
    for pattern in _DENIED_PATTERNS:
        if pattern.search(full_cmd):
            return False, "Command berisi pola berbahaya dan ditolak"

    return True, ""
