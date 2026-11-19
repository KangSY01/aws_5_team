"""Lambda 진입점 (Function URL / API Gateway HTTP API, payload v2.0).

뼈대 단계: 모든 경로가 app/data/ 의 샘플로 docs/api-contract.md 형식의 고정 응답을 돌려준다.
각 담당자는 아래 TODO 위치의 고정 응답을 실제 구현 호출로 바꾼다.

CORS 헤더는 여기서 붙이지 않는다. 배포에서는 Function URL 설정이,
로컬에서는 scripts/local_server.py 가 담당한다.
"""

import base64
import json
import logging
from pathlib import Path

from pydantic import BaseModel, TypeAdapter, ValidationError

from app.models.api import (
    ChatRequest,
    ChatResponse,
    CheckRequest,
    CheckResponse,
    ErrorBody,
    ErrorResponse,
    PlanResponse,
)
from app.models.plan import Place, Plan

logger = logging.getLogger(__name__)

# 샘플 데이터는 콜드 스타트 때 1회만 읽고 모델로 검증한다
_DATA = Path(__file__).parent / "data"


def _load(name: str) -> str:
    return (_DATA / name).read_text(encoding="utf-8")


PLACES = TypeAdapter(list[Place]).validate_json(_load("places.json"))
SAMPLE_PLAN = Plan.model_validate_json(_load("sample_plan.json"))
CHAT_RESPONSE = ChatResponse.model_validate_json(_load("chat_response.json"))
CHECK_RESPONSE = CheckResponse.model_validate_json(_load("check_response.json"))


class ApiError(Exception):
    """api-contract 오류 형식으로 바뀌는 예외."""

    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


def _response(status: int, model: BaseModel) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json; charset=utf-8"},
        "body": model.model_dump_json(),
    }


def _parse[T: BaseModel](event: dict, model: type[T]) -> T:
    """요청 본문을 모델로 읽는다. JSON 오류는 400, 검증 실패는 422."""
    body = event.get("body") or ""
    try:
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body)
        data = json.loads(body)
    except ValueError:
        raise ApiError(400, "bad_request", "요청 본문이 올바른 JSON이 아닙니다.")
    try:
        return model.model_validate(data)
    except ValidationError as e:
        detail = "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors())
        raise ApiError(422, "validation_error", detail)


def _require_plan(plan_id: str) -> None:
    if plan_id != SAMPLE_PLAN.plan_id:
        raise ApiError(404, "plan_not_found", f"{plan_id} 을 찾을 수 없습니다.")


def _plan_response(plan: Plan) -> PlanResponse:
    ids = {s.place_id for s in plan.stops}
    return PlanResponse(plan=plan, places=[p for p in PLACES if p.place_id in ids])


def _route(event: dict) -> BaseModel:
    method = event["requestContext"]["http"]["method"]
    parts = event["rawPath"].strip("/").split("/")

    match method, parts:
        case "POST", ["chat"]:
            _parse(event, ChatRequest)
            # TODO(에이전트 담당): app.agent.run_chat(request) 결과로 교체
            return CHAT_RESPONSE

        case "POST", ["plan", "check"]:
            request = _parse(event, CheckRequest)
            _require_plan(request.plan_id)
            # TODO(Guardian 담당): guardian.check_plan / propose_repairs 결과로 교체
            return CHECK_RESPONSE

        case "GET", ["plan", plan_id]:
            _require_plan(plan_id)
            # TODO(인프라 담당): app/storage 에서 읽기
            return _plan_response(SAMPLE_PLAN)

        case "PUT", ["plan", plan_id]:
            plan = _parse(event, Plan)
            if plan.plan_id != plan_id:
                raise ApiError(422, "validation_error", "본문의 plan_id 가 경로와 다릅니다.")
            _require_plan(plan_id)
            # TODO(인프라 담당): place_id 검증 후 app/storage 에 저장. 지금은 받은 일정을 그대로 돌려준다
            return _plan_response(plan)

        case _:
            raise ApiError(404, "not_found", f"{method} {event['rawPath']} 경로가 없습니다.")


def handler(event: dict, context=None) -> dict:
    try:
        return _response(200, _route(event))
    except ApiError as e:
        return _response(e.status, ErrorResponse(error=ErrorBody(code=e.code, message=e.message)))
    except Exception:
        logger.exception("요청 처리 중 오류")
        return _response(
            500, ErrorResponse(error=ErrorBody(code="internal_error", message="서버 오류가 발생했습니다."))
        )
