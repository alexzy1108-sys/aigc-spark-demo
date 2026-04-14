#!/usr/bin/env python3
"""
生花 Demo 本地全链路代理
运行：python3 local_proxy.py
监听 http://localhost:8766

转发规则：
  /seedance/*   → https://runway.devops.xiaohongshu.com/openai/doubao/contents/generations/tasks
  /spark/*      → http://shenghua-sparkwanghan.sl.beta.xiaohongshu.com/api/edith/spark/item/*
  其他          → 404
"""

import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── 配置 ────────────────────────────────────────────────
PORT = 8766

SEEDANCE_API_KEY = "698db1afe74941e0bad7e3827458f9bc"
SEEDANCE_BASE    = "https://runway.devops.xiaohongshu.com/openai/doubao/contents/generations/tasks"

SPARK_BASE       = "http://shenghua-sparkwanghan.sl.beta.xiaohongshu.com/api/edith/spark/item"
# ─────────────────────────────────────────────────────────


def do_upstream(method, url, headers, body=None):
    data = json.dumps(body).encode() if body else None
    req  = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as r:
            return r.status, r.read(), dict(r.headers)
    except HTTPError as e:
        return e.code, e.read(), {}
    except URLError as e:
        return 502, json.dumps({"error": str(e)}).encode(), {}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(f"[proxy] {self.command} {self.path}  →  {fmt % args}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, x-b3-traceid, x-b3-spanid")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    # ── /health ──────────────────────────────────────────
    def _handle_health(self):
        self._send(200, {"status": "ok"})

    # ── /seedance/task        POST → 创建任务 ────────────
    # ── /seedance/task/<id>   GET  → 查询状态 ────────────
    def _handle_seedance(self):
        headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {SEEDANCE_API_KEY}",
        }
        sub = self.path[len("/seedance"):]   # e.g. /task  or  /task/abc123

        if self.command == "POST" and sub == "/task":
            body = self._read_body()
            code, raw, _ = do_upstream("POST", SEEDANCE_BASE, headers, body)
            self._send_raw(code, raw)

        elif self.command == "GET" and sub.startswith("/task/"):
            task_id = sub[len("/task/"):]
            url = f"{SEEDANCE_BASE}/{task_id}"
            code, raw, _ = do_upstream("GET", url, headers)
            self._send_raw(code, raw)

        else:
            self._send(404, {"error": "unknown seedance path"})

    # ── /spark/<path>  →  生花平台 API ───────────────────
    def _handle_spark(self):
        sub = self.path[len("/spark"):]      # e.g. /brand-account-spu?...
        url = SPARK_BASE + sub

        # 透传 inbound headers（去掉 host）
        fwd_headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in ("host", "content-length")
        }
        fwd_headers.setdefault("Content-Type", "application/json")

        body = self._read_body() if self.command == "POST" else None
        code, raw, _ = do_upstream(self.command, url, fwd_headers, body)
        self._send_raw(code, raw)

    # ── 路由 ─────────────────────────────────────────────
    def _route(self):
        p = self.path.split("?")[0]
        if p == "/health":
            self._handle_health()
        elif p.startswith("/seedance"):
            self._handle_seedance()
        elif p.startswith("/spark"):
            self._handle_spark()
        else:
            self._send(404, {"error": f"no route for {p}"})

    do_GET  = _route
    do_POST = _route

    def _send(self, status, obj):
        self._send_raw(status, json.dumps(obj, ensure_ascii=False).encode())

    def _send_raw(self, status, raw):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"╔══════════════════════════════════════════════╗")
    print(f"║  生花 Demo 本地代理  http://localhost:{PORT}   ║")
    print(f"╠══════════════════════════════════════════════╣")
    print(f"║  /seedance/task         →  Seedance 2.0      ║")
    print(f"║  /spark/<path>          →  生花平台 API       ║")
    print(f"╚══════════════════════════════════════════════╝")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[proxy] 已停止")
