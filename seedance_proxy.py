#!/usr/bin/env python3
"""
Seedance 本地代理
运行：python3 seedance_proxy.py
监听 0.0.0.0:8766，转发到 runway.devops.xiaohongshu.com
"""

import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import urllib.parse

API_KEY   = "698db1afe74941e0bad7e3827458f9bc"
BASE_URL  = "https://runway.devops.xiaohongshu.com"
TASK_URL  = f"{BASE_URL}/openai/doubao/contents/generations/tasks"
PORT      = 8766

HEADERS = {
    "Content-Type":  "application/json",
    "Authorization": f"Bearer {API_KEY}",
}


def upstream_request(method, path, body=None):
    url = BASE_URL + path
    data = json.dumps(body).encode() if body else None
    req  = Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[proxy] {fmt % args}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length)) if length else {}

        # POST /task  →  创建任务
        if self.path == "/task":
            status, data = upstream_request("POST", "/openai/doubao/contents/generations/tasks", body)
            self._respond(status, data)

        else:
            self._respond(404, {"error": "not found"})

    def do_GET(self):
        # GET /task/<id>  →  查询状态
        if self.path.startswith("/task/"):
            task_id = self.path[len("/task/"):]
            status, data = upstream_request("GET", f"/openai/doubao/contents/generations/tasks/{task_id}")
            self._respond(status, data)

        else:
            self._respond(404, {"error": "not found"})

    def _respond(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[seedance proxy] 监听 0.0.0.0:{PORT}")
    print(f"[seedance proxy] POST http://localhost:{PORT}/task        → 创建任务")
    print(f"[seedance proxy] GET  http://localhost:{PORT}/task/<id>   → 查询状态")
    server.serve_forever()
