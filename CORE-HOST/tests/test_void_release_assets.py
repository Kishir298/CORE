"""Static checks for the release-grade Void Linux deployment assets."""
from __future__ import annotations

import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VOID = ROOT / "deployment" / "void"


def test_installer_guards_storage_versioned_venvs_and_rollback_state():
    text = (VOID / "install.sh").read_text()
    assert "risarms_require_void" in text
    assert "risarms_check_free_space" in text
    assert "venvs/$VERSION" in text
    assert "risarms_snapshot_install" in text
    assert "risarms_atomic_link" in text
    assert "risarms_write_state" in text
    assert "python3 -m venv /opt/risarms/core-venv" not in text
    assert "for script in backup.sh restore.sh upgrade.sh rollback.sh doctor.sh" in text


def test_installer_installs_log_configuration_and_runtime_lock_directory():
    text = (VOID / "install.sh").read_text()
    assert "log/config" in text
    assert "/run/risarms-inference" in text
    assert "nft -c -f /etc/nftables.conf" in text
    assert "caddy validate" in text


def test_runit_services_create_runtime_directories_and_drop_privileges():
    core = (VOID / "etc" / "sv" / "risarms-core" / "run").read_text()
    rescs = (VOID / "etc" / "sv" / "risarms-rescs" / "run").read_text()
    assert "install -d" in core and "/run/risarms-inference" in core
    assert "install -d" in rescs and "/var/lib/risarms/rescs/tmp" in rescs
    assert "chpst -u risarms:risarms" in core
    assert "chpst -u risarms:risarms" in rescs
    assert "umask 0077" in core and "umask 0077" in rescs


def test_runit_log_configuration_enforces_rotation():
    for name in ("risarms-core", "risarms-rescs"):
        config = (VOID / "etc" / "sv" / name / "log" / "config").read_text().splitlines()
        assert "s1048576" in config
        assert "n10" in config
        assert "t86400" in config


def test_backup_covers_data_configuration_and_retention():
    text = (VOID / "backup.sh").read_text()
    assert "etc/risarms" in text
    assert "var/lib/risarms/core" in text
    assert "var/lib/risarms/rescs" in text
    assert "sha256sum" in text
    assert "RISARMS_BACKUP_RETENTION_DAYS" in text
    assert "sv down risarms-core" in text


def test_restore_validates_archive_paths_and_rejects_symlinks():
    text = (VOID / "restore.sh").read_text()
    assert "allowed=" in text
    assert "unsafe paths" in text
    assert "symbolic links" in text
    assert "sha256sum -c" in text


def test_upgrade_and_rollback_use_versioned_venvs_and_health_checks():
    upgrade = (VOID / "upgrade.sh").read_text()
    rollback = (VOID / "rollback.sh").read_text()
    assert "sort -V" in upgrade
    assert "risarms_wait_http" in upgrade
    assert "risarms_previous_version" in rollback
    assert "risarms_atomic_link" in rollback
    assert "risarms_wait_http" in rollback


def test_doctor_checks_keys_permissions_services_and_health():
    text = (VOID / "doctor.sh").read_text()
    assert "RESCS key matches both gateway files" in text
    assert "configuration permissions are 0600" in text
    assert "CORE health endpoint responds" in text
    assert "RESCS readiness endpoint responds" in text
    assert "nft list table inet risarms" in text


def test_deployment_scripts_are_executable_and_parse():
    scripts = [
        VOID / "install.sh",
        VOID / "lib.sh",
        VOID / "backup.sh",
        VOID / "restore.sh",
        VOID / "upgrade.sh",
        VOID / "rollback.sh",
        VOID / "doctor.sh",
    ]
    for script in scripts:
        assert stat.S_IMODE(script.stat().st_mode) & stat.S_IXUSR
        subprocess.run(["bash", "-n", str(script)], check=True)
    for name in ("risarms-core", "risarms-rescs"):
        for relative in ("run", "log/run"):
            subprocess.run(
                ["sh", "-n", str(VOID / "etc" / "sv" / name / relative)],
                check=True,
            )
