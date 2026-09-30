"""CI workflow for an installed wheel, from outside the source directory.

Run with the clean environment's Python: python -I tests/installed_smoke.py.
"""
import io
from importlib.metadata import version
import json
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

import camwright


def main():
    assert version("camwright") == camwright.__version__
    with tempfile.TemporaryDirectory(prefix="camwright-installed-") as directory:
        child = subprocess.Popen([sys.executable, "-I", "-m", "camwright", "--no-browser"],
                                 cwd=directory, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            with selectors.DefaultSelector() as readiness:
                readiness.register(child.stdout, selectors.EVENT_READ)
                if not readiness.select(10):
                    raise AssertionError("installed launcher did not become ready")
            line = child.stdout.readline().strip()
            assert line.startswith("Camwright: http://127.0.0.1:"), line
            url = line.split(" ", 1)[1].rstrip("/")

            def request(path, data=None):
                raw = json.dumps(data).encode() if data is not None else None
                headers = {"Origin": url, "Content-Type": "application/json"}
                req = urllib.request.Request(url+path, data=raw, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=35) as response:
                        return response.status, response.headers, response.read()
                except urllib.error.HTTPError as response:
                    return response.code, response.headers, response.read()

            for asset in ["/", "/app.js", "/styles.css", "/favicon.svg"]:
                status, _, contents = request(asset)
                assert status == 200 and contents, asset
            status, _, raw = request("/api/example")
            assert status == 200
            project = json.loads(raw)
            status, _, raw = request("/api/check", {"project": project})
            checked = json.loads(raw)
            assert status == 200 and checked["result"]["status"] == "pass"

            def save_inspection(project, checked):
                status, headers, raw = request("/api/inspection", {"project": project,
                    "project_id": checked["project_id"], "inspection_id": checked["inspection_id"]})
                assert status == 200 and headers["Content-Type"] == "application/zip"
                with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
                    assert set(bundle.namelist()) == {"inspection.json", "inspection.html"}
                    record = json.loads(bundle.read("inspection.json"))
                    assert record["project"] == project and record["result"] == checked["result"]
                    assert record["implementation_version"] == version("camwright")
                    assert record["project_id"] == checked["project_id"]
                    assert record["inspection_id"] == checked["inspection_id"]
                    assert record["check_limits"] == checked["check_limits"]
                    assert b"Saved observation" in bundle.read("inspection.html")

            save_inspection(project, checked)
            status, headers, raw = request("/api/export", {"project": project, "project_id": checked["project_id"]})
            assert status == 200 and headers["Content-Type"] == "application/zip"
            with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
                assert len(bundle.namelist()) == 7
                assert json.loads(bundle.read("camwright-project.json")) == project
            project["base_radius"] = "20"
            status, _, raw = request("/api/check", {"project": project})
            failed = json.loads(raw)
            assert status == 200 and failed["result"]["status"] == "fail"
            status, headers, _ = request("/api/export", {"project": project, "project_id": failed["project_id"]})
            assert status == 409 and headers["Content-Type"] == "application/json"
            save_inspection(project, failed)
            unresolved = json.loads((Path(camwright.__file__).parent/"examples/unresolved.json").read_text())
            status, _, raw = request("/api/check", {"project": unresolved})
            checked = json.loads(raw)
            assert status == 200 and checked["result"]["status"] == "unknown"
            save_inspection(unresolved, checked)
            status, _, raw = request("/api/export", {"project": unresolved, "project_id": checked["project_id"]})
            assert status == 409 and "zip_base64" not in json.loads(raw)
            print("Installed workflow passed: assets, metadata, exact Pass/Fail/Unresolved inspection snapshots, complete geometry ZIP and refusal")
        finally:
            if child.poll() is None:
                child.send_signal(signal.SIGINT)
                try:
                    child.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.communicate()
            assert child.returncode == 0, f"installed launcher exit {child.returncode}"


if __name__ == "__main__":
    main()
