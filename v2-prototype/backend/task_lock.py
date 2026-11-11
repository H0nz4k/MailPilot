"""Interprocess lock for DataShip 2 task-store read-modify-write operations."""
from contextlib import contextmanager
from pathlib import Path
import os
import time


@contextmanager
def task_store_lock(directory, timeout=10):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / '.dataship-v2-tasks.lock'
    with path.open('a+b') as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, PermissionError, OSError) as exc:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Úlohy právě upravuje jiná instance DataShip 2. Zkuste to znovu.') from exc
                time.sleep(.05)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
