from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class LockAcquireError(RuntimeError):
    pass


@contextmanager
def file_lock(path: Path, timeout_sec: float = 1.0) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout_sec

    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(f"pid={os.getpid()} ts={int(time.time())}\n")
            break
        except FileExistsError as exc:
            if time.time() >= deadline:
                raise LockAcquireError(f"lock busy: {path}") from exc
            time.sleep(0.1)

    try:
        yield
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
