"""Custom exceptions for configbackup.

Keeping our own exception types means the CLI layer never has to know
about Netmiko's or smtplib's internals. Every low-level library error
gets caught close to its source and re-raised as one of these instead.
"""


class ConfigBackupError(Exception):
    """Base class for every error this package raises on purpose."""


class InventoryError(ConfigBackupError):
    """Raised when the inventory CSV is missing, empty, or malformed."""


class DeviceConnectionError(ConfigBackupError):
    """Raised when we cannot SSH into a device or pull its config.

    Wraps Netmiko's own exceptions (timeout, auth failure, SSH errors)
    so the rest of the program only has to catch one thing.
    """


class AlertError(ConfigBackupError):
    """Raised when the email alert cannot be sent."""
