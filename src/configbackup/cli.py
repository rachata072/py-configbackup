"""Command-line entry point: pull configs, diff, save, and alert.

Exit codes (checked in CI/cron so failures are easy to script around):
  0 - ran cleanly, every device backed up (whether it changed or not)
  1 - one or more devices could not be reached/backed up
  2 - bad arguments or an unusable inventory file (never touched SSH)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .alert import send_change_alert
from .backup import fetch_running_config
from .diffing import latest_backup, save_backup, unified_diff_text
from .exceptions import AlertError, DeviceConnectionError, InventoryError
from .inventory import load_inventory

DEFAULT_BACKUP_DIR = "backups"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="configbackup",
        description=(
            "Connect to every device in an inventory CSV over SSH, pull "
            "its running config, save a timestamped backup, diff it "
            "against the previous backup, and optionally email an "
            "alert when something changed."
        ),
    )
    parser.add_argument(
        "--inventory",
        required=True,
        help="Path to the inventory CSV file.",
    )
    parser.add_argument(
        "--backup-dir",
        default=DEFAULT_BACKUP_DIR,
        help=f"Directory to store backups in (default: {DEFAULT_BACKUP_DIR}).",
    )
    parser.add_argument(
        "--no-email",
        action="store_true",
        help="Skip sending an email alert even if configs changed.",
    )
    return parser


def _run_one_device(device, backup_dir: Path) -> tuple[str, str | None]:
    """Backup one device. Returns (hostname, diff_text_or_None).

    diff_text is None when this was the device's first backup (no
    previous file to diff against) or when nothing changed. Raises
    DeviceConnectionError if the device could not be reached, letting
    the caller decide how to record that failure.
    """
    config_text = fetch_running_config(device)
    previous_path = latest_backup(backup_dir, device.hostname)
    # Read the previous backup's content BEFORE writing the new one.
    # Timestamps now carry microsecond precision so a same-path
    # collision is not expected, but reading old-then-new in this
    # order is what actually guarantees a correct diff regardless.
    previous_text = previous_path.read_text(encoding="utf-8") if previous_path else None
    new_path = save_backup(backup_dir, device.hostname, config_text)

    if previous_path is None:
        print(f"[{device.hostname}] first backup saved: {new_path.name}")
        return device.hostname, None

    diff_text = unified_diff_text(
        previous_text,
        config_text,
        old_label=previous_path.name,
        new_label=new_path.name,
    )

    if diff_text:
        print(f"[{device.hostname}] CHANGED - saved {new_path.name}")
        return device.hostname, diff_text

    print(f"[{device.hostname}] no change - saved {new_path.name}")
    return device.hostname, None


def run(inventory_path: str, backup_dir: str, send_email: bool) -> int:
    try:
        devices = load_inventory(inventory_path)
    except InventoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    backup_dir_path = Path(backup_dir)
    failures: list[str] = []
    changed_devices: list[tuple[str, str]] = []

    for device in devices:
        try:
            hostname, diff_text = _run_one_device(device, backup_dir_path)
        except DeviceConnectionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            failures.append(device.hostname)
            continue

        if diff_text:
            changed_devices.append((hostname, diff_text))

    if changed_devices and send_email:
        try:
            send_change_alert(changed_devices)
            print(f"alert email sent for {len(changed_devices)} device(s).")
        except AlertError as exc:
            print(f"warning: {exc}", file=sys.stderr)
    elif changed_devices and not send_email:
        print("--no-email set, skipping alert email.")

    print(
        f"done: {len(devices)} device(s) in inventory, "
        f"{len(changed_devices)} changed, {len(failures)} failed."
    )

    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return run(
        inventory_path=args.inventory,
        backup_dir=args.backup_dir,
        send_email=not args.no_email,
    )


if __name__ == "__main__":
    sys.exit(main())
