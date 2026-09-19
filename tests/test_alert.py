from unittest.mock import MagicMock, patch

import pytest
import smtplib

from configbackup.alert import (
    build_alert_email,
    load_smtp_config_from_env,
    send_alert,
)
from configbackup.exceptions import AlertError

ENV_VARS = {
    "CONFIGBACKUP_SMTP_USERNAME": "me@gmail.com",
    "CONFIGBACKUP_SMTP_APP_PASSWORD": "abcd efgh ijkl mnop",
    "CONFIGBACKUP_ALERT_FROM": "me@gmail.com",
    "CONFIGBACKUP_ALERT_TO": "me@gmail.com, team@example.com",
}


def set_env(monkeypatch, overrides=None):
    values = {**ENV_VARS, **(overrides or {})}
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_load_smtp_config_from_env_defaults(monkeypatch):
    set_env(monkeypatch)
    config = load_smtp_config_from_env()
    assert config.host == "smtp.gmail.com"
    assert config.port == 587
    assert config.to_addrs == ["me@gmail.com", "team@example.com"]


def test_load_smtp_config_from_env_missing_vars_raises(monkeypatch):
    monkeypatch.delenv("CONFIGBACKUP_SMTP_USERNAME", raising=False)
    monkeypatch.delenv("CONFIGBACKUP_SMTP_APP_PASSWORD", raising=False)
    monkeypatch.delenv("CONFIGBACKUP_ALERT_FROM", raising=False)
    monkeypatch.delenv("CONFIGBACKUP_ALERT_TO", raising=False)

    with pytest.raises(AlertError, match="Missing required environment variable"):
        load_smtp_config_from_env()


def test_load_smtp_config_from_env_bad_port(monkeypatch):
    set_env(monkeypatch, {"CONFIGBACKUP_SMTP_PORT": "not-a-number"})
    with pytest.raises(AlertError, match="not a valid integer"):
        load_smtp_config_from_env()


def test_build_alert_email_lists_every_changed_device(monkeypatch):
    set_env(monkeypatch)
    config = load_smtp_config_from_env()
    changed = [("r1", "diff-for-r1"), ("r2", "diff-for-r2")]

    message = build_alert_email(config, changed)

    assert "r1" in message["Subject"]
    assert "r2" in message["Subject"]
    body = message.get_content()
    assert "diff-for-r1" in body
    assert "diff-for-r2" in body


@patch("configbackup.alert.smtplib.SMTP")
def test_send_alert_uses_starttls_and_login(mock_smtp_class, monkeypatch):
    set_env(monkeypatch)
    config = load_smtp_config_from_env()
    message = build_alert_email(config, [("r1", "diff")])

    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    send_alert(config, message)

    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with(config.username, config.app_password)
    mock_server.send_message.assert_called_once_with(message)


@patch("configbackup.alert.smtplib.SMTP")
def test_send_alert_wraps_auth_failure(mock_smtp_class, monkeypatch):
    set_env(monkeypatch)
    config = load_smtp_config_from_env()
    message = build_alert_email(config, [("r1", "diff")])

    mock_server = MagicMock()
    mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad creds")
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    with pytest.raises(AlertError, match="authentication failed"):
        send_alert(config, message)
