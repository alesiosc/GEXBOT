#!/usr/bin/env python3
"""
PID lock utility — prevents duplicate instances of a script.
Usage:
    from pid_lock import PIDLock
    
    lock = PIDLock("gamma_scraper")
    if not lock.acquire():
        print("Already running — exiting")
        sys.exit(0)
    # ... your code ...
    lock.release()
"""
import os, sys, signal, atexit

LOCK_DIR = os.path.dirname(os.path.abspath(__file__))


class PIDLock:
    """Simple PID file lock to prevent duplicate instances."""

    def __init__(self, name):
        self.name = name
        self.pid_file = os.path.join(LOCK_DIR, f"_{name}.pid")
        self.acquired = False

    def acquire(self):
        """Try to acquire the lock. Returns True if successful."""
        import subprocess
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file) as f:
                    raw = f.read().strip()
                if not raw:
                    raise ValueError("empty pid file")
                old_pid = int(raw)
                # Check if process is still alive
                if os.name == "nt":
                    result = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {old_pid}", "/FO", "CSV", "/NH"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if str(old_pid) in result.stdout:
                        print(f"  [{self.name}] Already running (PID {old_pid})", flush=True)
                        return False
                else:
                    try:
                        os.kill(old_pid, 0)
                        print(f"  [{self.name}] Already running (PID {old_pid})", flush=True)
                        return False
                    except OSError:
                        pass  # Process is dead, stale lock
            except (ValueError, OSError, subprocess.TimeoutExpired):
                pass  # Stale or unreadable lock file

        # Write our PID
        try:
            with open(self.pid_file, "w") as f:
                f.write(str(os.getpid()))
            self.acquired = True
            atexit.register(self.release)
            return True
        except OSError:
            return False

    def release(self):
        """Release the lock."""
        if self.acquired and os.path.exists(self.pid_file):
            try:
                with open(self.pid_file) as f:
                    stored_pid = f.read().strip()
                if stored_pid == str(os.getpid()):
                    os.remove(self.pid_file)
            except OSError:
                pass
            self.acquired = False
