"""Save timestamped config backups and diff against the previous one.

Layout on disk:

    backups/
      <hostname>/
        <hostname>_20260903-141055.cfg
        <hostname>_20260903-201412.cfg
        ...

Files sort correctly by name because the timestamp format
(YYYYMMDD-HHMMSS) is zero-padded and left-to-right chronological, so
"latest backup" is just "last file in a sorted listing" and never
needs to touch file modification times (which can be wrong if a file
was ever copied between machines).
"""

from __future__ import annotations

import difflib
from datetime import datetime
from pathlib import Path

# Includes microseconds on purpose. Seconds-only resolution sounds
# fine until the tool gets run twice in quick succession (a manual
# re-run while troubleshooting, or a test suite calling it twice in
# the same process) and two backups collide on the same filename,
# silently overwriting one of them.
TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S-%f"


def make_timestamp(now: datetime | None = None) -> str:
    """Return the current time formatted for use in a backup filename."""
    return (now or datetime.now()).strftime(TIMESTAMP_FORMAT)


def device_backup_dir(base_dir: Path, hostname: str) -> Path:
    """Return (and create) the backup folder for one device."""
    device_dir = Path(base_dir) / hostname
    device_dir.mkdir(parents=True, exist_ok=True)
    return device_dir


def list_backups(base_dir: Path, hostname: str) -> list[Path]:
    """Return every existing backup file for a device, oldest first."""
    device_dir = Path(base_dir) / hostname
    if not device_dir.is_dir():
        return []
    return sorted(device_dir.glob(f"{hostname}_*.cfg"))


def latest_backup(base_dir: Path, hostname: str) -> Path | None:
    """Return the most recent backup file for a device, or None."""
    backups = list_backups(base_dir, hostname)
    return backups[-1] if backups else None


def save_backup(
    base_dir: Path,
    hostname: str,
    config_text: str,
    timestamp: str | None = None,
) -> Path:
    """Write a new timestamped backup file and return its path."""
    device_dir = device_backup_dir(base_dir, hostname)
    stamp = timestamp or make_timestamp()
    backup_path = device_dir / f"{hostname}_{stamp}.cfg"
    backup_path.write_text(config_text, encoding="utf-8")
    return backup_path


def unified_diff_text(
    old_text: str,
    new_text: str,
    old_label: str,
    new_label: str,
) -> str:
    """Return a unified diff string between two config texts.

    Empty string if there's no difference at all, which callers use
    as the "did anything change" check.
    """
    diff_lines = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=old_label,
        tofile=new_label,
    )
    return "".join(diff_lines)
