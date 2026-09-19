"""Load and validate the device inventory CSV.

The inventory file is the single source of truth for which devices
this tool will connect to. Each row becomes a dict that gets handed
straight to Netmiko's ConnectHandler (after we resolve the password),
so we validate everything up front instead of failing halfway through
a run against real equipment.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from pathlib import Path

from .exceptions import InventoryError

# Columns every row must have. "password" and "password_env" are
# handled separately below since a row only needs one of the two.
REQUIRED_COLUMNS = {"hostname", "ip", "device_type", "username"}

# Netmiko default is 22, but we still want the column present in the
# CSV so it's obvious to a reader which port each device listens on.
DEFAULT_PORT = 22
DEFAULT_SECRET_ENV = ""


@dataclass
class Device:
    """One row of the inventory, ready to hand to Netmiko."""

    hostname: str
    ip: str
    device_type: str
    username: str
    password: str
    port: int = DEFAULT_PORT
    secret: str = ""
    # Extra keys we don't currently use but keep around for debugging
    # output / future columns without breaking anything.
    raw_row: dict = field(default_factory=dict, repr=False)

    def to_netmiko_dict(self) -> dict:
        """Build the kwargs dict Netmiko's ConnectHandler expects."""
        device_dict = {
            "device_type": self.device_type,
            "host": self.ip,
            "username": self.username,
            "password": self.password,
            "port": self.port,
        }
        if self.secret:
            device_dict["secret"] = self.secret
        return device_dict


def _resolve_password(row: dict, row_number: int) -> str:
    """Resolve a device's password from either an env var or the CSV.

    Preferring an environment variable (via a "password_env" column
    that names it) keeps real credentials out of the CSV file, which
    is what actually gets committed to git. A literal "password"
    column is still supported for a throwaway lab, since that is
    exactly the kind of environment this project is built to test
    against, but a warning is printed so it's never a silent choice.
    """
    password_env = (row.get("password_env") or "").strip()
    password_literal = (row.get("password") or "").strip()

    if password_env:
        value = os.environ.get(password_env)
        if not value:
            raise InventoryError(
                f"Row {row_number}: password_env is set to "
                f"'{password_env}' but that environment variable is "
                "not set (or is empty)."
            )
        return value

    if password_literal:
        print(
            f"[warning] Row {row_number} ({row.get('hostname', '?')}): "
            "reading a plaintext password directly from the inventory "
            "CSV. Use a 'password_env' column instead so real "
            "credentials never end up in a file you might commit.",
        )
        return password_literal

    raise InventoryError(
        f"Row {row_number}: no password found. Set either 'password' "
        "or 'password_env' for this device."
    )


def load_inventory(path: str | Path) -> list[Device]:
    """Read the inventory CSV and return a list of validated Device objects.

    Raises InventoryError for anything that would make a device
    unreachable: missing file, missing required column, empty file,
    duplicate hostnames, or a bad port number.
    """
    csv_path = Path(path)
    if not csv_path.is_file():
        raise InventoryError(f"Inventory file not found: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise InventoryError(f"Inventory file is empty: {csv_path}")

        header = {name.strip() for name in reader.fieldnames}
        missing = REQUIRED_COLUMNS - header
        if missing:
            raise InventoryError(
                "Inventory file is missing required column(s): "
                f"{', '.join(sorted(missing))}. Required columns are: "
                f"{', '.join(sorted(REQUIRED_COLUMNS))} (plus either "
                "'password' or 'password_env')."
            )

        devices: list[Device] = []
        seen_hostnames: set[str] = set()

        for row_number, row in enumerate(reader, start=2):  # header is line 1
            hostname = (row.get("hostname") or "").strip()
            ip = (row.get("ip") or "").strip()
            device_type = (row.get("device_type") or "").strip()
            username = (row.get("username") or "").strip()

            if not hostname or not ip or not device_type or not username:
                raise InventoryError(
                    f"Row {row_number}: hostname, ip, device_type, and "
                    "username must all be non-empty."
                )

            if hostname in seen_hostnames:
                raise InventoryError(
                    f"Row {row_number}: duplicate hostname '{hostname}'. "
                    "Backups are stored per-hostname, so each device "
                    "needs a unique name."
                )
            seen_hostnames.add(hostname)

            port_raw = (row.get("port") or "").strip()
            if port_raw:
                try:
                    port = int(port_raw)
                except ValueError as exc:
                    raise InventoryError(
                        f"Row {row_number}: port '{port_raw}' is not a "
                        "valid integer."
                    ) from exc
            else:
                port = DEFAULT_PORT

            password = _resolve_password(row, row_number)
            secret_env = (row.get("secret_env") or "").strip()
            secret = os.environ.get(secret_env, "") if secret_env else ""

            devices.append(
                Device(
                    hostname=hostname,
                    ip=ip,
                    device_type=device_type,
                    username=username,
                    password=password,
                    port=port,
                    secret=secret,
                    raw_row=row,
                )
            )

        if not devices:
            raise InventoryError(f"Inventory file has no device rows: {csv_path}")

        return devices
