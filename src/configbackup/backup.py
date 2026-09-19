"""Connect to a device with Netmiko and pull its running configuration.

This module knows nothing about diffing, file storage, or email. Its
only job is: given a Device, come back with the config text or raise
a DeviceConnectionError explaining what went wrong. Keeping it this
small makes it easy to unit test with a mocked ConnectHandler instead
of a real router.
"""

from __future__ import annotations

from netmiko import ConnectHandler
from netmiko.exceptions import (
    NetmikoAuthenticationException,
    NetmikoTimeoutException,
)

from .exceptions import DeviceConnectionError
from .inventory import Device

# Netmiko has a built-in command for a handful of platforms
# (cisco_ios, cisco_xe, arista_eos, juniper_junos, ...) but not every
# platform speaks "show running-config", so we keep an explicit map
# and fall back to a sane default for anything unlisted.
RUNNING_CONFIG_COMMANDS = {
    "cisco_ios": "show running-config",
    "cisco_xe": "show running-config",
    "cisco_nxos": "show running-config",
    "cisco_asa": "show running-config",
    "arista_eos": "show running-config",
    "juniper_junos": "show configuration",
    # VyOS doesn't have a flat running-config file the way IOS does;
    # "show configuration commands" prints the full config as a
    # deterministic, ordered list of "set" commands, which is the
    # closest equivalent and what VyOS's own docs recommend for
    # config backups.
    "vyos": "show configuration commands",
}
DEFAULT_COMMAND = "show running-config"

# How long to wait for the TCP/SSH handshake before giving up. Kept
# short on purpose: a lab device that isn't answering after 10
# seconds isn't going to answer at all, and a hung script is worse
# than a fast, clear failure.
CONNECT_TIMEOUT_SECONDS = 10
READ_TIMEOUT_SECONDS = 30


def get_running_config_command(device_type: str) -> str:
    """Return the right "show config" command for a device type."""
    return RUNNING_CONFIG_COMMANDS.get(device_type, DEFAULT_COMMAND)


def fetch_running_config(device: Device) -> str:
    """SSH into one device and return its running configuration text.

    Raises DeviceConnectionError (never a raw Netmiko exception) on
    any failure, with a message that says which device and why, so
    the CLI layer can report a clean per-device error instead of a
    stack trace.
    """
    command = get_running_config_command(device.device_type)
    connection_kwargs = device.to_netmiko_dict()
    connection_kwargs["conn_timeout"] = CONNECT_TIMEOUT_SECONDS

    try:
        with ConnectHandler(**connection_kwargs) as connection:
            config_text = connection.send_command(
                command, read_timeout=READ_TIMEOUT_SECONDS
            )
    except NetmikoAuthenticationException as exc:
        raise DeviceConnectionError(
            f"{device.hostname} ({device.ip}): authentication failed. "
            "Check the username/password (or password_env value) in "
            "the inventory."
        ) from exc
    except NetmikoTimeoutException as exc:
        raise DeviceConnectionError(
            f"{device.hostname} ({device.ip}): connection timed out "
            f"after {CONNECT_TIMEOUT_SECONDS}s. Check the IP, port, "
            "and that SSH is reachable from this machine."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - deliberately broad, see below
        # Netmiko can raise several other exception types depending on
        # the underlying transport (paramiko SSH errors, ValueError
        # for an unsupported device_type, etc). Rather than trying to
        # enumerate every one, we catch anything else here so a single
        # bad device can never crash the whole backup run, and still
        # surface the real error text for troubleshooting.
        raise DeviceConnectionError(
            f"{device.hostname} ({device.ip}): {exc.__class__.__name__}: {exc}"
        ) from exc

    return config_text
