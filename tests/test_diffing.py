from datetime import datetime

from configbackup.diffing import (
    latest_backup,
    list_backups,
    make_timestamp,
    save_backup,
    unified_diff_text,
)


def test_make_timestamp_format():
    stamp = make_timestamp(datetime(2026, 9, 3, 14, 10, 55, 123456))
    assert stamp == "20260903-141055-123456"


def test_save_backup_creates_file_with_expected_name(tmp_path):
    path = save_backup(
        tmp_path, "r1", "hostname r1\n", timestamp="20260903-141055-123456"
    )
    assert path.name == "r1_20260903-141055-123456.cfg"
    assert path.read_text() == "hostname r1\n"


def test_list_backups_sorted_oldest_first(tmp_path):
    save_backup(tmp_path, "r1", "v1\n", timestamp="20260901-000000-000000")
    save_backup(tmp_path, "r1", "v2\n", timestamp="20260902-000000-000000")
    save_backup(tmp_path, "r1", "v3\n", timestamp="20260903-000000-000000")

    backups = list_backups(tmp_path, "r1")

    assert [b.name for b in backups] == [
        "r1_20260901-000000-000000.cfg",
        "r1_20260902-000000-000000.cfg",
        "r1_20260903-000000-000000.cfg",
    ]


def test_list_backups_empty_when_no_directory(tmp_path):
    assert list_backups(tmp_path, "never-backed-up") == []


def test_latest_backup_returns_none_when_no_backups_exist(tmp_path):
    assert latest_backup(tmp_path, "r1") is None


def test_latest_backup_returns_most_recent_file(tmp_path):
    save_backup(tmp_path, "r1", "v1\n", timestamp="20260901-000000")
    newest = save_backup(tmp_path, "r1", "v2\n", timestamp="20260902-000000")

    assert latest_backup(tmp_path, "r1") == newest


def test_list_backups_does_not_mix_hostnames(tmp_path):
    save_backup(tmp_path, "r1", "v1\n", timestamp="20260901-000000")
    save_backup(tmp_path, "r2", "v1\n", timestamp="20260901-000000")

    assert len(list_backups(tmp_path, "r1")) == 1
    assert len(list_backups(tmp_path, "r2")) == 1


def test_unified_diff_text_empty_when_identical():
    diff = unified_diff_text("same\n", "same\n", "old.cfg", "new.cfg")
    assert diff == ""


def test_unified_diff_text_shows_changed_line():
    old = "interface eth0\n  address 10.0.0.1/24\n"
    new = "interface eth0\n  address 10.0.0.2/24\n"

    diff = unified_diff_text(old, new, "old.cfg", "new.cfg")

    assert "old.cfg" in diff
    assert "new.cfg" in diff
    assert "-  address 10.0.0.1/24" in diff
    assert "+  address 10.0.0.2/24" in diff
