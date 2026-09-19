import pytest

from configbackup.exceptions import InventoryError
from configbackup.inventory import load_inventory


def write_csv(tmp_path, content):
    path = tmp_path / "inventory.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_valid_inventory_with_password_env(tmp_path, monkeypatch):
    monkeypatch.setenv("R1_PW", "secret123")
    csv_path = write_csv(
        tmp_path,
        "hostname,ip,device_type,port,username,password_env,secret_env\n"
        "r1,10.0.0.1,vyos,22,admin,R1_PW,\n",
    )

    devices = load_inventory(csv_path)

    assert len(devices) == 1
    device = devices[0]
    assert device.hostname == "r1"
    assert device.ip == "10.0.0.1"
    assert device.device_type == "vyos"
    assert device.port == 22
    assert device.password == "secret123"


def test_loads_valid_inventory_with_literal_password(tmp_path, capsys):
    csv_path = write_csv(
        tmp_path,
        "hostname,ip,device_type,username,password\n"
        "r1,10.0.0.1,vyos,admin,labpassword\n",
    )

    devices = load_inventory(csv_path)

    assert devices[0].password == "labpassword"
    # A warning should be printed about plaintext passwords.
    captured = capsys.readouterr()
    assert "plaintext password" in captured.out


def test_default_port_is_22_when_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("R1_PW", "x")
    csv_path = write_csv(
        tmp_path,
        "hostname,ip,device_type,username,password_env\n"
        "r1,10.0.0.1,vyos,admin,R1_PW\n",
    )
    devices = load_inventory(csv_path)
    assert devices[0].port == 22


def test_missing_file_raises_inventory_error(tmp_path):
    with pytest.raises(InventoryError, match="not found"):
        load_inventory(tmp_path / "does-not-exist.csv")


def test_empty_file_raises_inventory_error(tmp_path):
    csv_path = write_csv(tmp_path, "")
    with pytest.raises(InventoryError, match="empty"):
        load_inventory(csv_path)


def test_no_device_rows_raises_inventory_error(tmp_path):
    csv_path = write_csv(
        tmp_path, "hostname,ip,device_type,username,password\n"
    )
    with pytest.raises(InventoryError, match="no device rows"):
        load_inventory(csv_path)


def test_missing_required_column_raises_inventory_error(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "hostname,ip,username,password\nr1,10.0.0.1,admin,pw\n",
    )
    with pytest.raises(InventoryError, match="missing required column"):
        load_inventory(csv_path)


def test_missing_password_raises_inventory_error(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "hostname,ip,device_type,username\nr1,10.0.0.1,vyos,admin\n",
    )
    with pytest.raises(InventoryError, match="no password found"):
        load_inventory(csv_path)


def test_missing_password_env_variable_raises_inventory_error(tmp_path):
    csv_path = write_csv(
        tmp_path,
        "hostname,ip,device_type,username,password_env\n"
        "r1,10.0.0.1,vyos,admin,NOT_SET_ANYWHERE\n",
    )
    with pytest.raises(InventoryError, match="NOT_SET_ANYWHERE"):
        load_inventory(csv_path)


def test_duplicate_hostname_raises_inventory_error(tmp_path, monkeypatch):
    monkeypatch.setenv("PW", "x")
    csv_path = write_csv(
        tmp_path,
        "hostname,ip,device_type,username,password_env\n"
        "r1,10.0.0.1,vyos,admin,PW\n"
        "r1,10.0.0.2,vyos,admin,PW\n",
    )
    with pytest.raises(InventoryError, match="duplicate hostname"):
        load_inventory(csv_path)


def test_invalid_port_raises_inventory_error(tmp_path, monkeypatch):
    monkeypatch.setenv("PW", "x")
    csv_path = write_csv(
        tmp_path,
        "hostname,ip,device_type,port,username,password_env\n"
        "r1,10.0.0.1,vyos,notaport,admin,PW\n",
    )
    with pytest.raises(InventoryError, match="not a valid integer"):
        load_inventory(csv_path)


def test_blank_required_field_raises_inventory_error(tmp_path, monkeypatch):
    monkeypatch.setenv("PW", "x")
    csv_path = write_csv(
        tmp_path,
        "hostname,ip,device_type,username,password_env\n"
        ",10.0.0.1,vyos,admin,PW\n",
    )
    with pytest.raises(InventoryError, match="must all be non-empty"):
        load_inventory(csv_path)


def test_to_netmiko_dict_includes_secret_only_when_present(tmp_path, monkeypatch):
    monkeypatch.setenv("PW", "x")
    monkeypatch.setenv("EN_PW", "enablepass")
    csv_path = write_csv(
        tmp_path,
        "hostname,ip,device_type,username,password_env,secret_env\n"
        "r1,10.0.0.1,cisco_ios,admin,PW,EN_PW\n"
        "r2,10.0.0.2,cisco_ios,admin,PW,\n",
    )
    devices = load_inventory(csv_path)
    d1 = devices[0].to_netmiko_dict()
    d2 = devices[1].to_netmiko_dict()
    assert d1["secret"] == "enablepass"
    assert "secret" not in d2
