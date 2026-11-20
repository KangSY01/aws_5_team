"""Lambda 진입점 (Function URL / API Gateway HTTP API, payload v2.0).

POST /chat 은 app.agent.run_chat 을 부른다 (FAKE_LLM=1 이면 run_chat 이 고정 응답을 돌려준다). 스트리밍은 아직 없다.
대화 처리 실패(ChatError: 시간 초과, 모델 오류, 답변 검증 실패)는 내부 사유를 숨기고 500 internal_error 로 바꾼다.
GET·PUT /plan 은 app/storage 에서 읽고 쓴다 (USE_MOCK=1 이면 메모리, 아니면 DynamoDB).
GET /events 는 app/data/events.json에서 조회 날짜가 전체 행사 기간에 포함된 행사를 모두 돌려준다.
/plan/check, /plan/{plan_id}/delay 는 저장된 일정을 읽어 Guardian(app/guardian/service.py) 결과를 돌려준다.
GET /alerts 는 예약 점검(app/scheduled_handler.py)이 저장한 마지막 결과를 읽기만 한다. 점검을 새로 하지 않는다.
POST /photo/upload-url, /photo/translate 는 app/photo/service.py 를 부른다 (USE_MOCK=1 이면 샘플 메뉴판, FAKE_LLM=1 이면 고정 번역).
POST /voice/url 은 app/voice/service.py 를 부른다 (Transcribe Streaming presigned URL. USE_MOCK=1 이면 연결되지 않는 가짜 주소).
Guardian 해결안은 저장하지 않는다. 사용자가 고른 해결안을 프론트엔드가 PUT /plan/{plan_id} 로 저장한다.

CORS 헤더는 여기서 붙이지 않는다. 배포에서는 Function URL 설정이,
로컬에서는 scripts/local_server.py 가 담당한다.
"""

import base64
import json
import logging
from pathlib import Path

from pydantic import BaseModel, TypeAdapter, ValidationError

from app import agent, storage
from app.guardian import service as guardian
from app.guardian.context import WeatherPresetNotFound
from app.models.api import (
    ChatRequest,
    ChatResponse,
    CheckRequest,
    CheckResponse,
    DelayRequest,
    ErrorBody,
    ErrorResponse,
    PhotoTranslateRequest,
    PhotoUploadUrlRequest,
    PlanResponse,
    SpeakRequest,
    SpeakResponse,
    VoiceUrlRequest,
)
from app.models.plan import Place, Plan
from app.photo import errors as photo_errors
from app.photo import service as photo
from app.speech import polly
from app.storage import InvalidDataError, PlanNotFoundError, StorageError
from app.tools import events_map
from app.tools.lookup import LookupFailure
from app.voice import service as voice
from app.voice.errors import VoiceServiceError

logger = logging.getLogger(__name__)

# 샘플 데이터는 콜드 스타트 때 1회만 읽고 모델로 검증한다
_DATA = Path(__file__).parent / "data"


def _load(name: str) -> str:
    return (_DATA / name).read_text(encoding="utf-8")


PLACES = TypeAdapter(list[Place]).validate_json(_load("places.json"))
PLACE_IDS = frozenset(place.place_id for place in PLACES)  # PUT /plan 이 받는 place_id 는 이 값뿐이다
SAMPLE_PLAN = Plan.model_validate_json(_load("sample_plan.json"))
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


def _check_places(plan: Plan) -> None:
    unknown = sorted({stop.place_id for stop in plan.stops} - PLACE_IDS)
    if unknown:
        raise ApiError(422, "validation_error", f"알 수 없는 place_id: {', '.join(unknown)}")


def _check_stops(plan: Plan) -> None:
    """stop_id 중복, 뒤집힌 시간 범위, Stop 사이의 시간 겹침을 거부한다. 앞 Stop 이 끝나는 시각에 다음 Stop 이 시작하는 것은 허용한다."""
    ids = [stop.stop_id for stop in plan.stops]
    duplicated = sorted({stop_id for stop_id in ids if ids.count(stop_id) > 1})
    if duplicated:
        raise ApiError(422, "validation_error", f"stop_id 가 겹칩니다: {', '.join(duplicated)}")
    for stop in plan.stops:
        if stop.start >= stop.end:
            raise ApiError(422, "validation_error", f"{stop.stop_id}: start 는 end 보다 앞서야 합니다.")
    ordered = sorted(plan.stops, key=lambda stop: stop.start)
    for prev, nxt in zip(ordered, ordered[1:]):
        if prev.end > nxt.start:
            raise ApiError(422, "validation_error", f"{prev.stop_id} 와 {nxt.stop_id} 의 시간이 겹칩니다.")


def _check_locked(stored: Plan, plan: Plan) -> None:
    """저장된 일정에서 locked 인 Stop 의 place_id·start·end 를 바꾸거나 빼는 요청을 거부한다.

    locked 값 자체는 바꿀 수 있다. 고정된 Stop 을 고치려면 먼저 locked 를 푸는 PUT 을 보낸다.
    """
    by_id = {stop.stop_id: stop for stop in plan.stops}
    for old in stored.stops:
        new = by_id.get(old.stop_id)
        if old.locked and (new is None or (new.place_id, new.start, new.end) != (old.place_id, old.start, old.end)):
            raise ApiError(422, "validation_error", f"고정된 일정 {old.stop_id} 는 바꿀 수 없습니다. 먼저 고정을 풀어 주세요.")


def _guardian(run):
    """Guardian 호출. 없는 demo.weather_preset 은 422 validation_error."""
    try:
        return run()
    except WeatherPresetNotFound as e:
        raise ApiError(422, "validation_error", str(e))


def _photo(run):
    """사진 인식 호출. app/photo/errors.py 의 예외를 api-contract 오류 형식으로 바꾼다.

    PhotoServiceError(설정 누락, AWS 호출 실패)의 사유는 app/photo 가 로그에 남기고, 응답에는 담지 않는다.
    """
    try:
        return run()
    except photo_errors.PhotoNotFound as e:
        raise ApiError(404, "not_found", str(e))
    except (photo_errors.PhotoKeyInvalid, photo_errors.PhotoUnreadable) as e:
        raise ApiError(422, "validation_error", str(e))
    except photo_errors.PhotoServiceError:
        raise ApiError(500, "internal_error", "서버 오류가 발생했습니다.")


def _events_response(date: str) -> events_map.EventsResponse:
    """지도 행사 조회의 날짜 오류만 계약의 422로 바꾼다."""
    try:
        return events_map.events_on_date(date)
    except LookupFailure as e:
        if e.code == "invalid_date":
            raise ApiError(422, "validation_error", e.message) from None
        raise


def _plan_response(plan: Plan) -> PlanResponse:
    ids = {s.place_id for s in plan.stops}
    places = [p for p in PLACES if p.place_id in ids]
    missing = ids - {p.place_id for p in places}
    if missing:  # PUT 이 막으므로 places.json 이 바뀐 경우에만 생긴다
        logger.warning("일정이 places.json 에 없는 장소를 참조합니다: %s", ", ".join(sorted(missing)))
    return PlanResponse(plan=plan, places=places)


def _route(event: dict) -> BaseModel:
    method = event["requestContext"]["http"]["method"]
    parts = event["rawPath"].strip("/").split("/")

    match method, parts:
        case "POST", ["chat"]:
            response = agent.run_chat(_parse(event, ChatRequest))
            if not isinstance(response, ChatResponse):  # ChatResponse 가 아닌 값은 응답으로 내보내지 않는다
                raise TypeError(f"run_chat 이 ChatResponse 가 아닌 {type(response).__name__} 을 돌려주었습니다.")
            return response

        case "POST", ["plan", "check"]:
            request = _parse(event, CheckRequest)
            plan = storage.get_plan(request.plan_id)
            return _guardian(lambda: guardian.run_check(plan, request.demo))

        case "POST", ["plan", plan_id, "delay"]:
            request = _parse(event, DelayRequest)
            if request.plan_id != plan_id:
                raise ApiError(422, "validation_error", "본문의 plan_id 가 경로와 다릅니다.")
            plan = storage.get_plan(plan_id)
            return _guardian(lambda: guardian.run_delay(plan, request.delay_min, request.demo))

        case "GET", ["events"]:
            date = ((event.get("queryStringParameters") or {}).get("date") or "").strip()
            if not date:
                raise ApiError(422, "validation_error", "date 쿼리 파라미터가 필요합니다.")
            return _events_response(date)

        case "GET", ["plan", plan_id]:
            return _plan_response(storage.get_plan(plan_id))

        case "PUT", ["plan", plan_id]:
            plan = _parse(event, Plan)
            if plan.plan_id != plan_id:
                raise ApiError(422, "validation_error", "본문의 plan_id 가 경로와 다릅니다.")
            stored = storage.get_plan(plan_id)  # 없으면 404. 본문이 잘못됐어도 없는 일정이면 404 가 먼저다
            _check_places(plan)
            _check_stops(plan)
            _check_locked(stored, plan)
            return _plan_response(storage.update_plan(plan))

        case "GET", ["alerts"]:
            plan_id = ((event.get("queryStringParameters") or {}).get("plan_id") or "").strip()
            if not plan_id:
                raise ApiError(422, "validation_error", "plan_id 쿼리 파라미터가 필요합니다.")
            return storage.get_alerts(plan_id)  # 없는 일정은 PlanNotFoundError → 404, 점검 전이면 checked_at null

        case "POST", ["speak"]:
            request = _parse(event, SpeakRequest)
            try:
                audio = polly.synthesize(request.text, request.language)
            except polly.SpeechError:  # 사유는 polly 가 로그에 남긴다. 계약 오류 표에 502 가 없어 500 으로 답한다
                raise ApiError(500, "internal_error", "음성을 만들지 못했습니다.")
            return SpeakResponse(content_type="audio/mpeg", audio_base64=base64.b64encode(audio).decode("ascii"))

        case "POST", ["photo", "upload-url"]:
            request = _parse(event, PhotoUploadUrlRequest)
            return _photo(lambda: photo.create_upload_url(request))

        case "POST", ["photo", "translate"]:
            request = _parse(event, PhotoTranslateRequest)
            return _photo(lambda: photo.translate_photo(request))

        case "POST", ["voice", "url"]:
            request = _parse(event, VoiceUrlRequest)
            try:
                return voice.create_voice_url(request)
            except VoiceServiceError:  # 사유는 app/voice 가 로그에 남긴다
                raise ApiError(500, "internal_error", "서버 오류가 발생했습니다.")

        case _:
            raise ApiError(404, "not_found", f"{method} {event['rawPath']} 경로가 없습니다.")


def handler(event: dict, context=None) -> dict:
    try:
        return _response(200, _route(event))
    except ApiError as e:
        return _response(e.status, ErrorResponse(error=ErrorBody(code=e.code, message=e.message)))
    except PlanNotFoundError as e:  # 세션 접근 거부(PlanAccessDeniedError)도 같은 404 로 나가 일정 존재 여부를 드러내지 않는다
        return _response(404, ErrorResponse(error=ErrorBody(code="plan_not_found", message=f"{e.plan_id} 을 찾을 수 없습니다.")))
    except InvalidDataError as e:
        return _response(422, ErrorResponse(error=ErrorBody(code="validation_error", message=str(e))))
    except agent.ChatError as e:  # 내부 사유(code)는 로그에만 남긴다. 상세 내용은 agent.py 가 이미 남겼다
        logger.error("대화 처리 실패: code=%s", e.code)
        return _response(
            500, ErrorResponse(error=ErrorBody(code="internal_error", message="서버 오류가 발생했습니다."))
        )
    except StorageError:  # DynamoDB 오류 내용은 저장소가 로그에 남기고, 클라이언트에는 알리지 않는다
        logger.error("저장소 오류로 요청을 처리하지 못했습니다.")
        return _response(
            500, ErrorResponse(error=ErrorBody(code="internal_error", message="서버 오류가 발생했습니다."))
        )
    except Exception:
        logger.exception("요청 처리 중 오류")
        return _response(
            500, ErrorResponse(error=ErrorBody(code="internal_error", message="서버 오류가 발생했습니다."))
        )
