#!/usr/bin/env python3
"""Simple runner script for AI GarminCoach."""

import atexit
import os
import signal
import sys
from dataclasses import dataclass


@dataclass
class InstanceLock:
    """Prevents more than one local run.py instance from starting."""

    lock_path: str
    locked: bool = False

    def acquire(self) -> None:
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        if os.path.exists(self.lock_path):
            existing_pid = self._read_pid()
            if existing_pid and self._is_process_alive(existing_pid):
                raise RuntimeError(
                    f"Another Garmin Coach instance is already running (pid={existing_pid})."
                )
            # Stale lock file from a crashed process.
            self._remove_lock_file()

        with open(self.lock_path, "w", encoding="utf-8") as lock_file:
            lock_file.write(str(os.getpid()))
            lock_file.flush()
            os.fsync(lock_file.fileno())

        self.locked = True
        atexit.register(self.release)

    def release(self) -> None:
        if not self.locked:
            return
        self._remove_lock_file()
        self.locked = False

    def _read_pid(self) -> int | None:
        try:
            with open(self.lock_path, "r", encoding="utf-8") as lock_file:
                raw_value = lock_file.read().strip()
            return int(raw_value) if raw_value else None
        except (OSError, ValueError):
            return None

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def _remove_lock_file(self) -> None:
        try:
            if os.path.exists(self.lock_path):
                os.remove(self.lock_path)
        except OSError:
            pass

# Add greenfield ADK app and legacy src to Python path.
repo_root = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(repo_root, "apps", "garmin_coach", "src"))
sys.path.insert(1, os.path.join(repo_root, "src"))

# Import and run main
from main import main
import asyncio

if __name__ == "__main__":
    lock = InstanceLock(lock_path=os.path.join(repo_root, ".run", "garmin-coach.pid"))
    try:
        lock.acquire()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    def _cleanup(*_: object) -> None:
        lock.release()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)

    try:
        asyncio.run(main())
    finally:
        lock.release()