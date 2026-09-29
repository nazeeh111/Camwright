import subprocess
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
