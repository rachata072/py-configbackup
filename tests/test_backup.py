from unittest.mock import MagicMock, patch

import pytest
from netmiko.exceptions import NetmikoAuthenticationException, NetmikoTimeoutException

from configbackup.backup import (
    _strip_noise_lines,
    fetch_running_config,
    get_running_config_command,
)
from configbackup.exceptions import DeviceConnectionError
from configbackup.inventory import Device


def make_device(device_type="cisco_ios"):
    return Device(
        hostname="r1",
        ip="10.0.0.1",
        device_type=device_type,
        username="admin",
        password="pw",
    )


def test_get_running_config_command_known_platform():
    assert get_running_config_command("cisco_ios") == "show running-config"
    assert get_running_config_command("vyos") == "show configuration commands"


def test_get_running_config_command_unknown_platform_falls_back():
    assert get_running_config_command("some_future_platform") == "show running-config"


@patch("configbackup.backup.ConnectHandler")
def test_fetch_running_config_returns_command_output(mock_connect_handler):
    mock_connection = MagicMock()
    mock_connection.send_command.return_value = "hostname r1\n!\nend\n"
    mock_connect_handler.return_value.__enter__.return_value = mock_connection

    result = fetch_running_config(make_device())

    assert result == "hostname r1\n!\nend\n"
    mock_connection.send_command.assert_called_once()
    called_command = mock_connection.send_command.call_args[0][0]
    assert called_command == "show running-config"


@patch("configbackup.backup.ConnectHandler")
def test_fetch_running_config_uses_platform_specific_command(mock_connect_handler):
    mock_connection = MagicMock()
    mock_connection.send_command.return_value = "set system host-name r1\n"
    mock_connect_handler.return_value.__enter__.return_value = mock_connection

    fetch_running_config(make_device(device_type="vyos"))

    called_command = mock_connection.send_command.call_args[0][0]
    assert called_command == "show configuration commands"


@patch("configbackup.backup.ConnectHandler")
def test_fetch_running_config_wraps_auth_failure(mock_connect_handler):
    mock_connect_handler.side_effect = NetmikoAuthenticationException("bad creds")

    with pytest.raises(DeviceConnectionError, match="authentication failed"):
        fetch_running_config(make_device())


@patch("configbackup.backup.ConnectHandler")
def test_fetch_running_config_wraps_timeout(mock_connect_handler):
    mock_connect_handler.side_effect = NetmikoTimeoutException("timed out")

    with pytest.raises(DeviceConnectionError, match="timed out"):
        fetch_running_config(make_device())


@patch("configbackup.backup.ConnectHandler")
def test_fetch_running_config_wraps_unexpected_error(mock_connect_handler):
    mock_connect_handler.side_effect = ValueError("unsupported device_type")

    with pytest.raises(DeviceConnectionError, match="ValueError"):
        fetch_running_config(make_device())


# --- Noise-line filtering ---------------------------------------------
#
# Found while testing against a real VyOS lab (not something a mocked
# test would have surfaced on its own, this test now encodes what was
# actually observed): a device's shell can leak lines into an SSH
# session's captured output that have nothing to do with its real
# configuration. Left in, these would show up as a permanent, bogus
# "change" on every single run.


def test_strip_noise_lines_removes_sudo_hostname_warning():
    raw = "set system host-name 'lab-r1'\nsudo: unable to resolve host lab-r1: System error\nset service ssh port 22\n"
    cleaned = _strip_noise_lines(raw)
    assert "sudo:" not in cleaned
    assert "set system host-name 'lab-r1'" in cleaned
    assert "set service ssh port 22" in cleaned


def test_strip_noise_lines_removes_bracketed_paste_toggle():
    raw = "[?2004l\nset system host-name 'lab-r1'\n"
    cleaned = _strip_noise_lines(raw)
    assert "[?2004l" not in cleaned
    assert "set system host-name 'lab-r1'" in cleaned


def test_strip_noise_lines_leaves_real_config_untouched():
    raw = "set system host-name 'lab-r1'\nset service ssh port 22\n"
    assert _strip_noise_lines(raw) == raw


@patch("configbackup.backup.ConnectHandler")
def test_fetch_running_config_filters_noise_from_real_output(mock_connect_handler):
    mock_connection = MagicMock()
    mock_connection.send_command.return_value = (
        "[?2004l\n"
        "set system host-name 'lab-r1'\n"
        "sudo: unable to resolve host lab-r1: System error\n"
        "set service ssh port 22\n"
    )
    mock_connect_handler.return_value.__enter__.return_value = mock_connection

    result = fetch_running_config(make_device(device_type="vyos"))

    assert result == "set system host-name 'lab-r1'\nset service ssh port 22\n"
