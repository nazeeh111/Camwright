"""Restricted localhost transport; requests never select filesystem paths."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import socket

from .engine import refused
from .project import MAX_BODY, derived, exact_keys, identity, parse_json, point, validate_project
from .runtime import Calculator

PACKAGE = Path(__file__).parent
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/styles.css": ("styles.css", "text/css; charset=utf-8"),
          "/favicon.svg": ("favicon.svg", "image/svg+xml")}
POST_KEYS = {"/api/validate": {"project"}, "/api/draft": {"project"}, "/api/check": {"project"},
             "/api/point": {"project", "angle_deg"},
             "/api/export": {"project", "project_id"}, "/api/cancel": {"project_id"}}


class Handler(BaseHTTPRequestHandler):
    server_version = "Camwright"

    def setup(self):
        super().setup()
        self.connection.settimeout(2)

    def log_message(self, format, *args):
        pass

    def send_bytes(self, status, contents, content_type, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(contents)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        for key, value in (headers or {}).items():
            self.send_header(key, str(value))
        self.end_headers()
        try:
            self.wfile.write(contents)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass

    def json(self, status, data):
        self.send_bytes(status, json.dumps(data, separators=(",", ":"), allow_nan=False).encode(), "application/json")

    def reject(self, status, code, message):
        self.json(status, {"error": {"code": code, "message": message}})

    def trusted_host(self):
        hosts = self.headers.get_all("Host", [])
        if hosts != [self.server.expected_host]:
            self.reject(403, "host", "Use the printed local Camwright URL")
            return False
        return True

    def do_GET(self):
        if not self.trusted_host():
            return
        if self.path == "/api/example":
            self.json(200, json.loads((PACKAGE / "examples/accepted.json").read_text()))
        elif self.path in STATIC:
            filename, content_type = STATIC[self.path]
            self.send_bytes(200, (PACKAGE / "static" / filename).read_bytes(), content_type)
        else:
            self.reject(404, "not_found", "Unknown endpoint")

    def do_POST(self):
        if not self.trusted_host():
            return
        if self.headers.get_all("Origin", []) != [self.server.expected_origin]:
            self.reject(403, "origin", "Same-origin requests are required")
            return
        if self.path not in POST_KEYS:
            self.reject(404, "not_found", "Unknown endpoint")
            return
        if self.headers.get_all("Content-Type", []) != ["application/json"]:
            self.reject(415, "content_type", "Use application/json")
            return
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get_all("Transfer-Encoding", []) or len(lengths) != 1 or re.fullmatch(r"[0-9]{1,6}", lengths[0]) is None:
            self.reject(400, "content_length", "A single bounded Content-Length is required")
            return
        length = int(lengths[0])
        if length > MAX_BODY:
            self.reject(413, "body_limit", "Request exceeds 32 KiB")
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("incomplete request body")
            request = parse_json(raw)
            exact_keys(request, POST_KEYS[self.path], "request")
            if self.path == "/api/cancel":
                project_id = request["project_id"]
                if not isinstance(project_id, str) or re.fullmatch(r"[a-f0-9]{64}", project_id) is None:
                    raise ValueError("invalid project identity")
                self.json(200, {"cancelled": self.server.calculator.cancel(project_id)})
                return
            project = validate_project(request["project"], require_closed=self.path != "/api/draft")
            if self.path == "/api/draft":
                self.json(200, {"derived": derived(project, require_closed=False)})
            elif self.path == "/api/validate":
                self.json(200, {"project": project, "project_id": identity(project), "derived": derived(project)})
            elif self.path == "/api/point":
                self.json(200, point(project, request["angle_deg"]))
            else:
                if self.path == "/api/export" and (not isinstance(request["project_id"], str) or
                        re.fullmatch(r"[a-f0-9]{64}", request["project_id"]) is None):
                    raise ValueError("invalid project identity")
                result = self.server.calculator.run("check" if self.path == "/api/check" else "export",
                                                    project, request.get("project_id"))
                if "error" in result:
                    self.json(429 if result["error"]["code"] == "busy" else 409, result)
                elif "zip_base64" in result:
                    summary = result["summary"]
                    self.send_bytes(200, base64.b64decode(result["zip_base64"]), "application/zip", {
                        "Content-Disposition": 'attachment; filename="camwright-profile.zip"',
                        "X-Camwright-Project-Id": result["project_id"],
                        "X-Camwright-Vertices": summary["vertices"],
                        "X-Camwright-Cam-Bound-Mm": summary["maximum_cam_bound_mm"],
                        "X-Camwright-Pitch-Bound-Mm": summary["maximum_pitch_bound_mm"]})
                else:
                    self.json(200, result)
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            self.reject(400, "invalid_project", str(error))
        except (socket.timeout, ConnectionResetError):
            self.reject(408, "request_timeout", "Request body was not received in time")

    def do_OPTIONS(self):
        self.reject(405, "method", "Use the documented GET and JSON POST endpoints")

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS


def make_server(port=0):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.expected_host = f"127.0.0.1:{server.server_address[1]}"
    server.expected_origin = f"http://{server.expected_host}"
    server.calculator = Calculator()
    return server
