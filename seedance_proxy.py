#!/usr/bin/env python3
"""
Seedance 本地代理（支持 HTTPS，解决 GitHub Pages mixed-content 限制）
运行：python3 seedance_proxy.py
监听 https://localhost:8766，转发到 runway.devops.xiaohongshu.com

首次运行会自动生成自签名证书 cert.pem / key.pem
Chrome 需要在 chrome://flags/#allow-insecure-localhost 开启，或访问一次 https://localhost:8766 手动信任证书
"""

import json
import ssl
import os
import subprocess
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API_KEY  = "698db1afe74941e0bad7e3827458f9bc"
BASE_URL = "https://runway.devops.xiaohongshu.com"
TASK_URL = f"{BASE_URL}/openai/doubao/contents/generations/tasks"
PORT     = 8766
CERT     = os.path.join(os.path.dirname(__file__), "seedance_cert.pem")
KEY      = os.path.join(os.path.dirname(__file__), "seedance_key.pem")

HEADERS = {
    "Content-Type":  "application/json",
    "Authorization": f"Bearer {API_KEY}",
}


def ensure_cert():
    if os.path.exists(CERT) and os.path.exists(KEY):
        return
    print("[proxy] 生成自签名证书...")
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048",
        "-keyout", KEY, "-out", CERT,
        "-days", "365", "-nodes",
        "-subj", "/CN=localhost",
        "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
    ], check=True, capture_output=True)
    print(f"[proxy] 证书生成完成：{CERT}")


def upstream(method, path, body=None):
    url  = BASE_URL + path
    data = json.dumps(body).encode() if body else None
    req  = Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
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
        if self.path == "/task":
            code, data = upstream("POST", "/openai/doubao/contents/generations/tasks", body)
            self._respond(code, data)
        else:
            self._respond(404, {"error": "not found"})

    def do_GET(self):
        if self.path.startswith("/task/"):
            task_id = self.path[len("/task/"):]
            code, data = upstream("GET", f"/openai/doubao/contents/generations/tasks/{task_id}")
            self._respond(code, data)
        else:
            # 健康检查 / 任意路径都返回 200 让 JS checkSeedanceProxy 能检测到
            self._respond(200, {"status": "ok"})

    def _respond(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type",   "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    ensure_cert()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT, KEY)

    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.socket = ctx.wrap_socket(server.socket, server_side=True)

    print(f"[seedance proxy] HTTPS 监听 https://localhost:{PORT}")
    print(f"[seedance proxy] POST https://localhost:{PORT}/task        → 创建任务")
    print(f"[seedance proxy] GET  https://localhost:{PORT}/task/<id>   → 查询状态")
    print()
    print("⚠️  首次使用需要信任证书：")
    print(f"   1. 在浏览器打开 https://localhost:{PORT}")
    print(f"   2. 点「高级」→「继续访问」，信任证书")
    print(f"   3. 回到 demo 页面，刷新后重试")
    server.serve_forever()
