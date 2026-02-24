from __future__ import annotations

from pathlib import Path

from agos.lock import LockAcquireError, file_lock


def test_file_lock_exclusive(tmp_path: Path) -> None:
    lock_file = tmp_path / "bouncer.lock"
    with file_lock(lock_file, timeout_sec=0.1):
        try:
            with file_lock(lock_file, timeout_sec=0.1):
                raise AssertionError("expected lock contention")
        except LockAcquireError:
            pass

    with file_lock(lock_file, timeout_sec=0.1):
        assert lock_file.exists()
