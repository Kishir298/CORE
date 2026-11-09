"""
A.S.I.S. virtual environment setup (uv-based).

Creates a Python 3.12 virtual environment and installs the light runtime
dependencies plus development tooling. Voice dependencies are excluded;
install them separately with:

    uv pip install -r requirements/voice.txt

Notes on Windows + Application Control policies
-----------------------------------------------
Some Windows machines enforce an executable policy (WDAC/AppLocker) that
allows known CPython interpreter binaries but blocks the small "venv
launcher" redirectors normally placed in ``Scripts\\python.exe``. To stay
compatible, this script builds a "classic" venv layout:

    1.  ``python -m venv --without-pip``  (never spawns the launcher)
    2.  copy the full interpreter into ``Scripts\\``
    3.  install dependencies with ``uv pip install --python ...``

This layout also works on unrestricted machines, so it is used everywhere.

Requirements:
    uv  (https://docs.astral.sh/uv/)
"""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PYTHON_VERSION = "3.12"
VENV_DIR = ROOT / ".venv"


def ensure_uv() -> None:
    if shutil.which("uv") is None:
        raise RuntimeError(
            "uv was not found on PATH. Install it from https://docs.astral.sh/uv/"
        )


def get_base_python() -> str:
    """Locate a uv-managed CPython matching PYTHON_VERSION.

    Prefers a standalone interpreter (not this project's venv) so that
    interpreter files can safely be copied from it.
    """
    commands = (
        ["uv", "python", "find", "--system", PYTHON_VERSION],
        ["uv", "python", "find", PYTHON_VERSION],
    )

    for command in commands:
        result = subprocess.run(
            command,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            continue

        candidate = result.stdout.strip().splitlines()[-1].strip()
        if candidate:
            return candidate

    raise RuntimeError(f"uv could not locate Python {PYTHON_VERSION}.")


def create_venv(base_python: str) -> None:
    if (VENV_DIR / "pyvenv.cfg").exists():
        print(f"Virtual environment already exists: {VENV_DIR}")
        return

    print(f"Creating virtual environment with Python {PYTHON_VERSION}...")
    subprocess.check_call([base_python, "-m", "venv", "--without-pip", str(VENV_DIR)])


def install_venv_interpreter(base_python: str) -> None:
    """Place full interpreter binaries in Scripts (classic venv layout).

    Existing files are left untouched so re-runs are safe even when the
    venv interpreter is currently executing this script.
    """
    scripts = VENV_DIR / "Scripts"
    base_dir = Path(base_python).parent

    if platform.system() == "Windows":
        major, minor = PYTHON_VERSION.split(".")

        for name in (
            "python.exe",
            "pythonw.exe",
            "python3.dll",
            f"python{major}{minor}.dll",
        ):
            source = base_dir / name
            target = scripts / name

            if source.exists() and target.exists():
                continue

            if source.exists() and source.resolve() != target.resolve():
                shutil.copy2(source, target)

        dlls_dir = base_dir / "DLLs"
        target_dlls = scripts / "DLLs"

        if dlls_dir.exists():
            target_dlls.mkdir(parents=True, exist_ok=True)

            for entry in dlls_dir.iterdir():
                if entry.is_file() and not (target_dlls / entry.name).exists():
                    shutil.copy2(entry, target_dlls / entry.name)
    else:
        # On Unix-like systems the venv interpreter is a symlink and needs
        # no special handling.
        return


def install_dependencies() -> None:
    python = VENV_DIR / "Scripts" / "python.exe"

    if platform.system() != "Windows":
        python = VENV_DIR / "bin" / "python"

    if not python.exists():
        raise RuntimeError(f"Venv interpreter missing: {python}")

    print("Installing runtime and development dependencies...")
    subprocess.check_call(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "-r",
            "requirements.txt",
            "-r",
            "requirements/development.txt",
        ],
        cwd=str(ROOT),
    )


def main() -> None:
    print(f"Detected OS: {platform.system()}")
    ensure_uv()

    base_python = get_base_python()
    print(f"Base interpreter: {base_python}")

    create_venv(base_python)
    install_venv_interpreter(base_python)
    install_dependencies()

    print()
    print("A.S.I.S. virtual environment: READY")
    print(f"Python: {PYTHON_VERSION}")
    print()

    if platform.system() == "Windows":
        activate = f"{VENV_DIR.name}\\Scripts\\Activate.ps1"
    else:
        activate = f"source {VENV_DIR.name}/bin/activate"

    print(f"Activate it with:  {activate}")
    print("Note: use `uv pip ...` for dependency management.")


if __name__ == "__main__":
    main()
