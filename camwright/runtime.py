"""One calculation at a time, with a real process deadline and cleanup."""
import json
from datetime import datetime, timezone
from pathlib import Path
import secrets
import subprocess
import sys
import threading

from .engine import refused
from .inspection import MAX_INSPECTION_BYTES, build_archive
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
        self.inspection = None
        self.inspection_generation = 0

    def invalidate_inspection(self):
        with self.lock:
            self.inspection = None
            self.inspection_generation += 1

    def save_inspection(self, project, project_id, inspection_id):
        with self.lock:
            snapshot = self.inspection
            if (self.closed or snapshot is None or project_id != identity(project) or
                    project_id != snapshot[0] or inspection_id != snapshot[1]):
                return refused("stale_inspection", "Check the current project before saving its inspection")
            contents = snapshot[2]
        try:
            return build_archive(contents)
        except ValueError as error:
            return refused("output_limit", str(error))

    def run(self, operation, project, project_id=None):
        if not self.slot.acquire(blocking=False):
            return refused("busy", "A calculation is already running")
        child = None
        try:
            payload = json.dumps({"operation": operation, "project": project,
                                  "project_id": project_id}, separators=(",", ":")).encode()
            project = json.loads(payload)["project"]
            with self.lock:
                if self.closed:
                    return refused("cancelled", "The local server is closing")
                if operation == "check":
                    self.inspection = None
                    self.inspection_generation += 1
                    generation = self.inspection_generation
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
            if child.returncode != 0 or len(output) > 16 * 1024 * 1024:
                with self.lock:
                    if self.cancelled:
                        return refused("cancelled", "Calculation was cancelled")
                return refused("worker_failed", "Calculation could not complete within its limits")
            result = json.loads(output)
            with self.lock:
                if self.cancelled or self.closed:
                    return refused("cancelled", "Calculation was cancelled")
                if operation == "check" and "error" not in result:
                    if generation != self.inspection_generation:
                        return refused("superseded_check", "A newer check request replaced this inspection")
                    receipt = secrets.token_hex(16)
                    document = {"schema": "camwright.inspection", "version": 1,
                                "inspection_id": receipt, "project_id": result["project_id"],
                                "completed_at_utc": datetime.now(timezone.utc).isoformat(),
                                "implementation_version": result["implementation_version"],
                                "check_limits": result["check_limits"], "worker_deadline_seconds": self.deadline,
                                "model": project["model"], "units": project["units"],
                                "angle_units": project["angle_units"], "project": project,
                                "result": result["result"], "derived": result["derived"]}
                    snapshot = json.dumps(document, separators=(",", ":"), allow_nan=False).encode()
                    if len(snapshot) > MAX_INSPECTION_BYTES:
                        return refused("output_limit", "Inspection exceeds the bounded record size")
                    self.inspection = (result["project_id"], receipt, snapshot)
                    result["inspection_id"] = receipt
            return result
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
            self.inspection = None
            if self.active.poll() is None:
                self.active.kill()
            return True

    def close(self):
        with self.lock:
            self.closed = True
            self.inspection = None
            child = self.active
            if self.active is not None:
                self.cancelled = True
                if self.active.poll() is None:
                    self.active.kill()
        if child is not None:
            child.wait(timeout=2)
