from unittest.mock import patch

from configbackup.cli import main
from configbackup.exceptions import DeviceConnectionError


def write_inventory(tmp_path, monkeypatch, hostnames=("r1",)):
    rows = ["hostname,ip,device_type,username,password_env"]
    for name in hostnames:
        env_name = f"{name.upper()}_PW"
        monkeypatch.setenv(env_name, "pw")
        rows.append(f"{name},10.0.0.1,cisco_ios,admin,{env_name}")
    csv_path = tmp_path / "inventory.csv"
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return csv_path


def test_first_run_creates_baseline_and_exits_zero(tmp_path, monkeypatch):
    csv_path = write_inventory(tmp_path, monkeypatch)
    backup_dir = tmp_path / "backups"

    with patch("configbackup.cli.fetch_running_config", return_value="config-v1\n"):
        exit_code = main(
            ["--inventory", str(csv_path), "--backup-dir", str(backup_dir)]
        )

    assert exit_code == 0
    saved = list((backup_dir / "r1").glob("r1_*.cfg"))
    assert len(saved) == 1
    assert saved[0].read_text() == "config-v1\n"


def test_second_run_with_change_sends_alert(tmp_path, monkeypatch):
    csv_path = write_inventory(tmp_path, monkeypatch)
    backup_dir = tmp_path / "backups"

    with patch("configbackup.cli.fetch_running_config", return_value="config-v1\n"):
        main(["--inventory", str(csv_path), "--backup-dir", str(backup_dir)])

    with (
        patch("configbackup.cli.fetch_running_config", return_value="config-v2\n"),
        patch("configbackup.cli.send_change_alert") as mock_send_alert,
    ):
        exit_code = main(
            ["--inventory", str(csv_path), "--backup-dir", str(backup_dir)]
        )

    assert exit_code == 0
    mock_send_alert.assert_called_once()
    changed_devices_arg = mock_send_alert.call_args[0][0]
    assert changed_devices_arg[0][0] == "r1"
    assert "config-v1" in changed_devices_arg[0][1] or "-config-v1" in changed_devices_arg[0][1]


def test_second_run_no_change_does_not_alert(tmp_path, monkeypatch):
    csv_path = write_inventory(tmp_path, monkeypatch)
    backup_dir = tmp_path / "backups"

    with patch("configbackup.cli.fetch_running_config", return_value="same-config\n"):
        main(["--inventory", str(csv_path), "--backup-dir", str(backup_dir)])

    with (
        patch("configbackup.cli.fetch_running_config", return_value="same-config\n"),
        patch("configbackup.cli.send_change_alert") as mock_send_alert,
    ):
        exit_code = main(
            ["--inventory", str(csv_path), "--backup-dir", str(backup_dir)]
        )

    assert exit_code == 0
    mock_send_alert.assert_not_called()


def test_no_email_flag_suppresses_alert_even_when_changed(tmp_path, monkeypatch):
    csv_path = write_inventory(tmp_path, monkeypatch)
    backup_dir = tmp_path / "backups"

    with patch("configbackup.cli.fetch_running_config", return_value="config-v1\n"):
        main(["--inventory", str(csv_path), "--backup-dir", str(backup_dir)])

    with (
        patch("configbackup.cli.fetch_running_config", return_value="config-v2\n"),
        patch("configbackup.cli.send_change_alert") as mock_send_alert,
    ):
        exit_code = main(
            [
                "--inventory",
                str(csv_path),
                "--backup-dir",
                str(backup_dir),
                "--no-email",
            ]
        )

    assert exit_code == 0
    mock_send_alert.assert_not_called()


def test_device_connection_failure_gives_exit_code_one(tmp_path, monkeypatch):
    csv_path = write_inventory(tmp_path, monkeypatch, hostnames=("r1", "r2"))
    backup_dir = tmp_path / "backups"

    def fake_fetch(device):
        if device.hostname == "r1":
            raise DeviceConnectionError("r1: connection timed out")
        return "config-r2\n"

    with patch("configbackup.cli.fetch_running_config", side_effect=fake_fetch):
        exit_code = main(
            ["--inventory", str(csv_path), "--backup-dir", str(backup_dir)]
        )

    assert exit_code == 1
    # r2 should still have been backed up even though r1 failed.
    assert list((backup_dir / "r2").glob("r2_*.cfg"))
    assert not (backup_dir / "r1").exists()


def test_bad_inventory_path_gives_exit_code_two(tmp_path):
    exit_code = main(
        ["--inventory", str(tmp_path / "missing.csv"), "--backup-dir", str(tmp_path)]
    )
    assert exit_code == 2


def test_alert_failure_does_not_crash_run(tmp_path, monkeypatch):
    from configbackup.exceptions import AlertError

    csv_path = write_inventory(tmp_path, monkeypatch)
    backup_dir = tmp_path / "backups"

    with patch("configbackup.cli.fetch_running_config", return_value="config-v1\n"):
        main(["--inventory", str(csv_path), "--backup-dir", str(backup_dir)])

    with (
        patch("configbackup.cli.fetch_running_config", return_value="config-v2\n"),
        patch(
            "configbackup.cli.send_change_alert",
            side_effect=AlertError("smtp down"),
        ),
    ):
        exit_code = main(
            ["--inventory", str(csv_path), "--backup-dir", str(backup_dir)]
        )

    # Email failing is a warning, not a run failure: backups still count as done.
    assert exit_code == 0
