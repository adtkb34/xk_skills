#!/usr/bin/env python3
"""Local HTTP server for backlog dashboard with CSV save."""

from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

from build_html import (
    api_payload,
    append_execution_row,
    append_item_row,
    build_backlog_html,
    parse_backlog,
    resolve_backlog_dir,
)


class BacklogHandler(BaseHTTPRequestHandler):
    backlog_dir: Path
    html_path: Path

    def log_message(self, fmt: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        path = unquote(self.path.split("?", 1)[0])
        if path in ("/", "/index.html"):
            self._serve_file(self.html_path)
            return
        if path == "/api/data":
            md_path = resolve_backlog_dir(self.backlog_dir)
            data = parse_backlog(md_path)
            self._send_json(200, api_payload(data))
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        path = unquote(self.path.split("?", 1)[0])
        if path == "/api/items":
            try:
                body = self._read_json_body()
                payload = append_item_row(self.backlog_dir, body)
                self._send_json(201, payload)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})
            return
        if path == "/api/executions":
            try:
                body = self._read_json_body()
                payload = append_execution_row(self.backlog_dir, body)
                self._send_json(201, payload)
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})
            return
        self.send_error(404, "Not found")

    def _serve_file(self, file_path: Path) -> None:
        if not file_path.is_file():
            self.send_error(404, "Not found")
            return
        content = file_path.read_bytes()
        mime, _ = mimetypes.guess_type(str(file_path))
        self.send_response(200)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def run_server(backlog_dir: Path, port: int, html_path: Path) -> None:
    build_backlog_html(backlog_dir, html_path, editor_enabled=True)
    BacklogHandler.backlog_dir = backlog_dir
    BacklogHandler.html_path = html_path.resolve()
    server = ThreadingHTTPServer(("127.0.0.1", port), BacklogHandler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Serving {html_path.name} at {url} (CSV save enabled; Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
