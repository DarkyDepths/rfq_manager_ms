import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class MockEventBusHandler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self._send_json(200, {"status": "ok", "service": "mock_event_bus"})
            return

        self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length > 0 else b"{}"

        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except json.JSONDecodeError:
            payload = {"_raw": raw_body.decode("utf-8", errors="replace")}

        print("\n=== EVENT RECEIVED ===", flush=True)
        print(f"path: {self.path}", flush=True)
        print(json.dumps(payload, indent=2, sort_keys=True), flush=True)

        self._send_json(200, {"received": True})

    def log_message(self, format, *args):
        return


def main():
    host = "0.0.0.0"
    port = 8081
    httpd = HTTPServer((host, port), MockEventBusHandler)
    print(f"mock_event_bus listening on http://{host}:{port}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
