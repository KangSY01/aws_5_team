"""handler 를 로컬에서 직접 호출한다. backend/ 에서 실행한다.

    uv run python -m scripts.local_invoke                       # 샘플 호출 전부
    uv run python -m scripts.local_invoke GET /plan/plan-1      # 한 건만
    uv run python -m scripts.local_invoke GET "/alerts?plan_id=plan-1"   # 쿼리 파라미터는 경로 뒤에 붙인다
    uv run python -m scripts.local_invoke POST /plan/check '{"plan_id": "plan-1"}'
"""

import json
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit

from app.handler import SAMPLE_PLAN, handler


def make_event(method: str, path: str, body: str | None = None, query: dict[str, str] | None = None) -> dict:
    """Lambda Function URL (payload v2.0) 형식의 이벤트를 만든다. path 에는 쿼리를 넣지 않고 query 로 넘긴다."""
    event = {
        "version": "2.0",
        "rawPath": path,
        "requestContext": {"http": {"method": method, "path": path}},
        "body": body,
        "isBase64Encoded": False,
    }
    if query:
        event["rawQueryString"] = urlencode(query)
        event["queryStringParameters"] = dict(query)
    return event


def _samples() -> list[tuple[str, str, str | None]]:
    plan_id = SAMPLE_PLAN.plan_id
    chat = {"plan_id": plan_id, "message": "雨なら屋内に変えて", "profile": {"language": "ja"}}
    return [
        ("POST", "/chat", json.dumps(chat, ensure_ascii=False)),
        ("GET", f"/plan/{plan_id}", None),
        ("PUT", f"/plan/{plan_id}", SAMPLE_PLAN.model_dump_json()),
        ("POST", "/plan/check", json.dumps({"plan_id": plan_id})),
    ]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 에서 파이프로 넘겨도 다국어가 깨지지 않게
    calls = [tuple(sys.argv[1:4])] if len(sys.argv) > 2 else _samples()
    for method, target, *body in calls:
        parts = urlsplit(target)
        result = handler(make_event(method, parts.path, body[0] if body else None, dict(parse_qsl(parts.query))))
        print(f"== {method} {target} -> {result['statusCode']}")
        print(json.dumps(json.loads(result["body"]), ensure_ascii=False, indent=2))
