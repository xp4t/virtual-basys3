"""Local companion HTTP service, sharing the live simulator state."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/logic.js": ("logic.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/analyzer.css": ("analyzer.css", "text/css; charset=utf-8"),
          "/basys3.jpg": ("../basys3.jpg", "image/jpeg")}


class Handler(BaseHTTPRequestHandler):
    def send(self, status, content, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/state":
            self.send(200, json.dumps(self.server.runtime.snapshot()).encode())
        elif path == "/api/logic/catalog":
            self.send(200, json.dumps(self.server.runtime.logic_catalog()).encode())
        elif path == "/api/logic":
            self.send(200, json.dumps(self.server.runtime.logic_snapshot()).encode())
        elif path == "/api/logic.csv":
            try:
                self.send(200, self.server.runtime.logic_csv().encode(), "text/csv; charset=utf-8")
            except ValueError as error:
                self.send(409, json.dumps({"error": str(error)}).encode())
        elif path in STATIC:
            filename, content_type = STATIC[path]
            self.send(200, (ROOT / "board-visualizer" / filename).read_bytes(), content_type)
        else:
            self.send(404, b'{"error":"Not found"}')

    def do_POST(self):
        if self.path not in ("/api/control", "/api/logic"):
            self.send(404, b'{"error":"Not found"}')
            return
        try:
            # Same-origin browser control; no broad CORS permission.
            origin = self.headers.get("Origin")
            if origin and urlsplit(origin).netloc != self.headers.get("Host"):
                self.send(403, b'{"error":"Cross-origin control rejected"}')
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 4096:
                raise ValueError("Invalid body size")
            if self.headers.get_content_type() != "application/json":
                raise ValueError("Expected application/json")
            command = json.loads(self.rfile.read(length))
            result = (self.server.runtime.logic_control(command) if self.path == "/api/logic"
                      else self.server.runtime.control(command))
            self.send(200, json.dumps(result).encode())
        except (ValueError, KeyError, TypeError) as error:
            self.send(400, json.dumps({"error": str(error)}).encode())

    def log_message(self, *args):
        pass


def create_http_server(address, runtime):
    server = ThreadingHTTPServer(address, Handler)
    server.daemon_threads = True
    server.runtime = runtime
    return server
