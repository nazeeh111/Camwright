"""One calculation at a time, with a real process deadline and cleanup."""
import json
from pathlib import Path
import subprocess
import sys
import threading

from .engine import refused
from .project import identity


class Calculator:
    def __init__(self, *, deadline=30, command=None):
        self.deadline = deadline
        self.command = command or [sys.executable, "-I", str(Path(__file__).with_name("worker.py"))]
        self.slot = threading.Semaphore(1)
        self.lock = threading.Lock()
        self.active = None
        self.active_id = None
        self.cancelled = False
        self.closed = False

    def run(self, operation, project, project_id=None):
        if not self.slot.acquire(blocking=False):
            return refused("busy", "A calculation is already running")
        child = None
        try:
            payload = json.dumps({"operation": operation, "project": project,
                                  "project_id": project_id}, separators=(",", ":")).encode()
            with self.lock:
                if self.closed:
                    return refused("cancelled", "The local server is closing")
                child = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE)
                self.active = child
                self.active_id = identity(project)
                self.cancelled = False
            try:
                output, _ = child.communicate(payload, timeout=self.deadline)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()
                return refused("deadline", "Calculation exceeded the 30-second deadline")
            with self.lock:
                cancelled = self.cancelled
            if cancelled:
                return refused("cancelled", "Calculation was cancelled")
            if child.returncode != 0 or len(output) > 16 * 1024 * 1024:
                return refused("worker_failed", "Calculation could not complete within its limits")
            return json.loads(output)
        except (OSError, ValueError):
            return refused("worker_failed", "The local calculation process could not complete")
        finally:
            if child is not None and child.poll() is None:
                child.kill()
                child.communicate()
            with self.lock:
                self.active = None
                self.active_id = None
                self.cancelled = False
            self.slot.release()

    def cancel(self, project_id):
        with self.lock:
            if self.active is None or self.active_id != project_id:
                return False
            self.cancelled = True
            if self.active.poll() is None:
                self.active.kill()
            return True

    def close(self):
        with self.lock:
            self.closed = True
            child = self.active
            if self.active is not None:
                self.cancelled = True
                if self.active.poll() is None:
                    self.active.kill()
        if child is not None:
            child.wait(timeout=2)
