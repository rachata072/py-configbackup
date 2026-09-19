"""Send an email alert when one or more device configs changed.

Credentials are read from environment variables, never from a
command-line flag or a file that would end up in git. The intended
setup is a Gmail account with an App Password (Google Account ->
Security -> 2-Step Verification -> App passwords), which lets this
script authenticate over SMTP without touching the account's real
password. See RUNBOOK.md for the exact steps.
"""

from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from .exceptions import AlertError

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587

ENV_SMTP_HOST = "CONFIGBACKUP_SMTP_HOST"
ENV_SMTP_PORT = "CONFIGBACKUP_SMTP_PORT"
ENV_SMTP_USERNAME = "CONFIGBACKUP_SMTP_USERNAME"
ENV_SMTP_APP_PASSWORD = "CONFIGBACKUP_SMTP_APP_PASSWORD"
ENV_ALERT_FROM = "CONFIGBACKUP_ALERT_FROM"
ENV_ALERT_TO = "CONFIGBACKUP_ALERT_TO"


@dataclass
class SmtpConfig:
    host: str
    port: int
    username: str
    app_password: str
    from_addr: str
    to_addrs: list[str]


def load_smtp_config_from_env() -> SmtpConfig:
    """Build an SmtpConfig from environment variables.

    Raises AlertError listing every missing variable at once (instead
    of one at a time) so a misconfigured environment can be fixed in
    a single pass.
    """
    username = os.environ.get(ENV_SMTP_USERNAME, "").strip()
    app_password = os.environ.get(ENV_SMTP_APP_PASSWORD, "").strip()
    from_addr = os.environ.get(ENV_ALERT_FROM, "").strip()
    to_addrs_raw = os.environ.get(ENV_ALERT_TO, "").strip()

    missing = [
        name
        for name, value in (
            (ENV_SMTP_USERNAME, username),
            (ENV_SMTP_APP_PASSWORD, app_password),
            (ENV_ALERT_FROM, from_addr),
            (ENV_ALERT_TO, to_addrs_raw),
        )
        if not value
    ]
    if missing:
        raise AlertError(
            "Missing required environment variable(s) for email "
            f"alerts: {', '.join(missing)}. See RUNBOOK.md for how to "
            "set these up with a Gmail App Password."
        )

    to_addrs = [addr.strip() for addr in to_addrs_raw.split(",") if addr.strip()]

    host = os.environ.get(ENV_SMTP_HOST, DEFAULT_SMTP_HOST).strip()
    port_raw = os.environ.get(ENV_SMTP_PORT, str(DEFAULT_SMTP_PORT)).strip()
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise AlertError(f"{ENV_SMTP_PORT} is not a valid integer: {port_raw!r}") from exc

    return SmtpConfig(
        host=host,
        port=port,
        username=username,
        app_password=app_password,
        from_addr=from_addr,
        to_addrs=to_addrs,
    )


def build_alert_email(
    smtp_config: SmtpConfig,
    changed_devices: list[tuple[str, str]],
) -> EmailMessage:
    """Build the alert email for a list of (hostname, diff_text) pairs."""
    hostnames = [hostname for hostname, _diff in changed_devices]
    subject = (
        f"[configbackup] config change detected on {len(hostnames)} "
        f"device(s): {', '.join(hostnames)}"
    )

    body_parts = [
        f"configbackup detected a running-config change on "
        f"{len(hostnames)} device(s):\n",
    ]
    for hostname, diff_text in changed_devices:
        body_parts.append(f"\n{'=' * 60}\n{hostname}\n{'=' * 60}\n")
        body_parts.append(diff_text if diff_text else "(no diff text captured)\n")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_config.from_addr
    message["To"] = ", ".join(smtp_config.to_addrs)
    message.set_content("".join(body_parts))
    return message


def send_alert(smtp_config: SmtpConfig, message: EmailMessage) -> None:
    """Send an already-built EmailMessage over SMTP with STARTTLS.

    Raises AlertError on any SMTP failure (auth, connection, etc).
    """
    try:
        with smtplib.SMTP(smtp_config.host, smtp_config.port, timeout=15) as server:
            server.starttls()
            server.login(smtp_config.username, smtp_config.app_password)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise AlertError(
            "SMTP authentication failed. If this is Gmail, confirm "
            f"{ENV_SMTP_USERNAME} is your full email address and "
            f"{ENV_SMTP_APP_PASSWORD} is a 16-character App Password, "
            "not your normal account password."
        ) from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise AlertError(f"Failed to send alert email: {exc}") from exc


def send_change_alert(changed_devices: list[tuple[str, str]]) -> None:
    """Convenience wrapper: load env config, build, and send in one call."""
    smtp_config = load_smtp_config_from_env()
    message = build_alert_email(smtp_config, changed_devices)
    send_alert(smtp_config, message)
