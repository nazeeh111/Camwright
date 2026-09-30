import subprocess
from pathlib import Path
import sys
import threading
import time
import unittest

from camwright.runtime import Calculator
from camwright.project import identity
from .test_project import example


class RuntimeTests(unittest.TestCase):
    def sleeper(self, deadline):
        return Calculator(deadline=deadline, command=[sys.executable, "-I", "-c", "import time; time.sleep(10)"])

    def test_real_timeout_kills_and_reaps_child_then_releases_slot(self):
        runner = self.sleeper(.1)
        started = time.monotonic()
        result = runner.run("check", example())
        self.assertEqual("deadline", result["error"]["code"])
        self.assertLess(time.monotonic()-started, 2)
        self.assertIsNone(runner.active)
        self.assertTrue(runner.slot.acquire(blocking=False))
        runner.slot.release()

    def test_busy_and_matching_cancel_do_not_leave_worker(self):
        runner = self.sleeper(5)
        result = []
        thread = threading.Thread(target=lambda: result.append(runner.run("check", example())))
        thread.start()
        limit = time.monotonic()+2
        while runner.active is None and time.monotonic()<limit:
            time.sleep(.01)
        self.assertIsNotNone(runner.active)
        child = runner.active
        self.assertEqual("busy", runner.run("check", example())["error"]["code"])
        self.assertFalse(runner.cancel("0"*64))
        self.assertTrue(runner.cancel(identity(example())))
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertIsNotNone(child.poll())
        self.assertEqual("cancelled", result[0]["error"]["code"])

    def test_real_bundled_worker_returns_current_result(self):
        runner = Calculator()
        result = runner.run("check", example())
        self.assertEqual("pass", result["result"]["status"])
        self.assertEqual(identity(example()), result["project_id"])

    def test_new_check_cancel_and_close_invalidate_completed_inspection(self):
        runner = Calculator()
        project = example()
        checked = runner.run("check", project)
        self.assertIn("inspection_id", checked)
        runner.command = [sys.executable, "-I", "-c", "import time; time.sleep(10)"]
        result = []
        thread = threading.Thread(target=lambda: result.append(runner.run("check", project)))
        thread.start()
        limit = time.monotonic()+2
        while runner.active is None and time.monotonic()<limit:
            time.sleep(.01)
        self.assertIsNotNone(runner.active)
        self.assertIn("error", runner.save_inspection(project, identity(project), checked["inspection_id"]))
        self.assertTrue(runner.cancel(identity(project)))
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual("cancelled", result[0]["error"]["code"])
        self.assertIn("error", runner.save_inspection(project, identity(project), checked["inspection_id"]))
        runner.close()
        self.assertIn("error", runner.save_inspection(project, identity(project), checked["inspection_id"]))

    def test_invalidated_active_check_cannot_restore_a_replaced_snapshot(self):
        # The real native worker still calculates; the wrapper only widens the
        # race window between worker execution and result delivery.
        worker = str(Path(__file__).parents[1]/"camwright/worker.py")
        script = ("import subprocess,sys,time; "
                  f"r=subprocess.run([{sys.executable!r},'-I',{worker!r}],input=sys.stdin.buffer.read(),capture_output=True,check=True); "
                  "time.sleep(.2); sys.stdout.buffer.write(r.stdout)")
        runner = Calculator(command=[sys.executable, "-I", "-c", script])
        project = example()
        result = []
        thread = threading.Thread(target=lambda: result.append(runner.run("check", project)))
        thread.start()
        limit = time.monotonic()+2
        while runner.active is None and time.monotonic()<limit:
            time.sleep(.01)
        self.assertIsNotNone(runner.active)
        runner.invalidate_inspection()
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual("superseded_check", result[0]["error"]["code"])
        self.assertIn("error", runner.save_inspection(project, identity(project), "0"*32))
        runner.close()
