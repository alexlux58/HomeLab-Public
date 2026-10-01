"""arr_backup copies the newest valid zip, verifies it, and never overwrites."""

import os
import time
import zipfile

import pytest
from arr_backup import BackupError, copy_one


def _zip(path, content=b"db"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("radarr.db", content)


def test_copies_the_newest_backup_with_a_checksum(tmp_path):
    source = tmp_path / "scheduled"
    source.mkdir()
    old, new = source / "radarr_backup_old.zip", source / "radarr_backup_new.zip"
    _zip(old)
    _zip(new, b"newer")
    past = time.time() - 3600
    os.utime(old, (past, past))
    result = copy_one("radarr", source, tmp_path / "dest")
    assert "copied radarr_backup_new.zip" in result
    assert (tmp_path / "dest/radarr/radarr_backup_new.zip").is_file()
    assert (tmp_path / "dest/radarr/radarr_backup_new.zip.sha256").is_file()


def test_never_overwrites_an_existing_copy(tmp_path):
    source = tmp_path / "scheduled"
    source.mkdir()
    _zip(source / "b.zip")
    copy_one("radarr", source, tmp_path / "dest")
    assert "already copied" in copy_one("radarr", source, tmp_path / "dest")


def test_a_corrupt_backup_is_refused(tmp_path):
    source = tmp_path / "scheduled"
    source.mkdir()
    (source / "bad.zip").write_bytes(b"not a zip")
    with pytest.raises(BackupError):
        copy_one("radarr", source, tmp_path / "dest")
    assert not (tmp_path / "dest/radarr/bad.zip").exists()


def test_an_empty_source_is_an_error(tmp_path):
    (tmp_path / "scheduled").mkdir()
    with pytest.raises(BackupError):
        copy_one("radarr", tmp_path / "scheduled", tmp_path / "dest")
