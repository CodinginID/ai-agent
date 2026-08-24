from __future__ import annotations

import subprocess
from pathlib import Path

from app.safety.policy import validate_args

DEFAULT_TIMEOUT: int = 20


def run_safe(
    args: list[str],
    cwd: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
) -> tuple[str, int]:
    """
    Run a subprocess after policy validation.
    Returns (output, exit_code). exit_code is -1 on policy violation or error.
    Output includes exit code prefix when non-zero.
    """
    allowed, reason = validate_args(args)
    if not allowed:
        return f"Command ditolak: {reason}", -1

    try:
        result = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except FileNotFoundError:
        return f"Command tidak ditemukan: {args[0]}", -1
    except subprocess.TimeoutExpired:
        return f"Command timeout setelah {timeout} detik.", -1
    except Exception as exc:
        return f"Gagal menjalankan command: {exc}", -1

    output = result.stdout.strip()
    if result.returncode != 0:
        output = f"Exit code: {result.returncode}\n{output}"

    return output, result.returncode
