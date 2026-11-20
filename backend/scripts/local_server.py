"""handler 를 로컬 HTTP 서버로 띄운다 (프론트엔드 연결용). backend/ 에서 실행한다.

    uv run python -m scripts.local_server          # http://127.0.0.1:8000
    uv run python -m scripts.local_server 9000     # 포트 변경

개발 전용. CORS 를 전부 허용하므로 외부에 노출하지 않는다 (127.0.0.1 에만 바인딩).
"""

import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

from app.handler import handler
from scripts.local_invoke import make_event

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, OPTIONS",
    "Access-Control-Allow-Headers": "content-type",
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, headers: dict, body: bytes = b"") -> None:
        self.send_response(status)
        for name, value in {**headers, **CORS, "Content-Length": str(len(body))}.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # CORS 사전 요청
        self._send(204, {})

    def _invoke(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8", errors="replace") if length else None
        target = urlsplit(self.path)
        result = handler(make_event(self.command, target.path, body, dict(parse_qsl(target.query))))
        self._send(result["statusCode"], result["headers"], result["body"].encode("utf-8"))

    do_GET = do_POST = do_PUT = _invoke


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"로컬 서버 시작: http://127.0.0.1:{port} (Ctrl+C 로 종료)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
