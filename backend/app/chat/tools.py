"""대화 에이전트가 쓰는 도구: 조회 도구 묶음, 일정 생성 도구(PlanCreator), 호출 제한·기록 훅(ToolRecorder).

- 조회 도구는 B 의 app/tools/lookup.py 것을 그대로 등록한다. 새로 만들지 않는다.
- 일정 생성: 모델은 place_id 만 고르고, 방문 순서와 시각은 B 의 build_plan 이 계산한다. 도구는 일정을 저장하지 않고
  요청 범위에 보관(staged)만 한다. 저장은 답변 검증이 끝난 뒤 run_chat 이 한다.
- 일정 수정 도구는 app/tools/plan_edit.py 의 PlanEditor 를 쓴다.
"""

import datetime as dt
import json
import logging
import threading
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from strands import tool
from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry

from app.chat.messages import BUILD_ERROR_KEYS
from app.chat.plan_rules import load_places, place_name, validate_plan
from app.models.plan import Plan, Profile
from app.tools.lookup import get_crowd, get_events, get_hours, get_travel_time, get_weather, search_places
from app.tools.schedule import PlanBuildError, build_plan

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 5  # 한 요청에서 실행할 수 있는 도구 호출 총수 (team.md)
MIN_PLACES, MAX_PLACES = 3, 5  # 새 일정의 장소 수 (요구사항 2.1)

# B 가 구현한 조회 도구 전부. get_place_info 는 없다.
LOOKUP_TOOLS = [search_places, get_crowd, get_weather, get_hours, get_travel_time, get_events]


def place_ids_in(result: Any) -> list[str]:
    """search_places 결과(Place dict 목록)에서 place_id 만 꺼낸다. 오류 dict 나 이상한 항목은 무시한다."""
    if not isinstance(result, list):
        return []
    return [item["place_id"] for item in result if isinstance(item, dict) and isinstance(item.get("place_id"), str)]


@dataclass
class ToolOutput:
    """성공한 도구 호출 하나. data 는 도구가 돌려준 값(JSON 으로 읽은 것)."""

    name: str
    args: dict
    data: Any


def _payload(result: dict) -> Any | None:
    """Strands ToolResult 에서 도구 반환값을 꺼낸다. dict·list 는 JSON 문자열로 들어온다."""
    for item in result.get("content", []):
        if "json" in item:
            return item["json"]
        if "text" in item:
            try:
                return json.loads(item["text"])
            except ValueError:
                return None
    return None


class ToolRecorder(HookProvider):
    """도구 호출을 5회로 제한하고, 성공한 결과를 요청 범위에 모은다.

    한도를 넘은 호출은 실행하지 않고 "이제 답하라"는 메시지로 막는다(Strands cancel_tool). 오류 dict 를 돌려준
    도구(B 의 도구는 실패해도 status 가 success 다)는 outputs 에 넣지 않고 errors 로 센다.
    """

    def __init__(self, max_calls: int = MAX_TOOL_CALLS):
        self.max_calls = max_calls
        self.outputs: list[ToolOutput] = []
        self.counts: Counter[str] = Counter()  # 실행을 허용한 호출 (도구 이름별)
        self.errors: Counter[str] = Counter()  # 실패한 호출
        self.rejected = 0  # 한도 때문에 막은 호출 수
        self._rejected_ids: set[str] = set()
        self._listeners: list[Callable[[str, Any], None]] = []
        self._lock = threading.Lock()

    def on_output(self, listener: Callable[[str, Any], None]) -> None:
        """성공한 도구 결과마다 listener(도구 이름, 반환값)를 부른다."""
        self._listeners.append(listener)

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self._before)
        registry.add_callback(AfterToolCallEvent, self._after)

    def _before(self, event: BeforeToolCallEvent) -> None:
        with self._lock:
            over = sum(self.counts.values()) >= self.max_calls
            if over:
                self.rejected += 1
                self._rejected_ids.add(event.tool_use["toolUseId"])
            else:
                self.counts[event.tool_use["name"]] += 1
        if over:
            event.cancel_tool = (
                f"Tool call limit reached ({self.max_calls}). Do not call any more tools. "
                "Answer now using only the results you already have."
            )

    def _after(self, event: AfterToolCallEvent) -> None:
        name = event.tool_use["name"]
        try:
            if event.tool_use["toolUseId"] in self._rejected_ids:
                return
            data = _payload(event.result) if event.result.get("status") == "success" else None
            if data is None or (isinstance(data, dict) and "error" in data):
                self.errors[name] += 1
                return
            self.outputs.append(ToolOutput(name, dict(event.tool_use.get("input") or {}), data))
            for listener in self._listeners:
                listener(name, data)
        except Exception:  # 기록 실패가 대화를 끊지 않게 한다
            logger.exception("도구 결과 기록 중 오류")


class PlanCreator:
    """새 일정을 만드는 도구 하나(create_plan)와 그 상태. 요청마다 하나 만든다."""

    def __init__(self, profile: Profile, today: dt.date, plan_id: str):
        self.profile = profile
        self.today = today
        self.plan_id = plan_id  # 만들어질 일정의 ID. 서버가 발급한 값이라 build_plan 의 해시 ID 를 쓰지 않는다
        self.plan: Plan | None = None  # 만든 일정 (아직 저장 전)
        self.notice: str | None = None  # 마지막 시도가 실패했을 때 사용자에게 줄 안내 키 (messages.py)
        self._candidates: set[str] = set()  # 이 요청에서 search_places 가 돌려준 장소 ID

    @property
    def tools(self) -> list:
        return [self.create_plan]

    def allow_search_results(self, result: Any) -> None:
        self._candidates.update(place_ids_in(result))

    def _fail(self, notice: str, code: str, message: str) -> dict:
        """실패한 시도. 앞서 만든 유효한 일정(self.plan)은 지우지 않는다. notice 는 일정이 없을 때만 쓰인다."""
        self.notice = notice
        return {"error": {"code": code, "message": message}}

    @tool
    def create_plan(self, place_ids: list[str], date: str | None = None, start: str | None = None) -> dict:
        """Create a one-day itinerary from places you found with search_places.

        Use this when the user asks for an itinerary and has none yet. Call it once, after you have chosen the
        places. The system decides the visiting order, the stay length and the times, so never compute them.

        Args:
            place_ids: 3 to 5 distinct place_id values. Every one must come from a search_places result in this
                conversation turn.
            date: Trip date as YYYY-MM-DD. Omit it to use TODAY.
            start: Start time of the first stop as HH:MM (24-hour). Omit it to start at 10:00.

        Returns:
            On success: {"plan_id", "date", "stops": [{"stop_id", "place_id", "name", "start", "end"}]} with times
            in ISO 8601 (+09:00). Describe the plan only with these values.
            On failure: {"error": {"code", "message"}}. Codes: unknown_place, place_not_searched, bad_place_count,
            no_valid_places, invalid_date, invalid_start, data_unavailable, plan_invalid.
        """
        places = load_places()
        unique = list(dict.fromkeys(p for p in place_ids if isinstance(p, str)))
        unknown = [p for p in unique if p not in places]
        unsearched = [p for p in unique if p in places and p not in self._candidates]
        usable = [p for p in unique if p in places and p in self._candidates]
        if unknown or unsearched:
            notice = "incomplete" if usable else "no_valid_places"
            if unknown:
                return self._fail(notice, "unknown_place", f"These place_ids do not exist: {', '.join(unknown)}.")
            return self._fail(
                notice,
                "place_not_searched",
                f"These place_ids were not returned by search_places in this turn: {', '.join(unsearched)}. "
                "Call search_places and use place_ids from its result.",
            )
        if not usable:
            return self._fail("no_valid_places", "no_valid_places", "No valid place_id was given.")
        if not MIN_PLACES <= len(usable) <= MAX_PLACES:
            return self._fail(
                "incomplete", "bad_place_count", f"Choose {MIN_PLACES} to {MAX_PLACES} distinct places; got {len(usable)}."
            )
        try:
            plan = build_plan(usable, date or self.today, start, self.profile, plan_id=self.plan_id)
        except PlanBuildError as error:
            logger.warning("일정 생성 실패: 사유=%s", error.code)
            return self._fail(error.code if error.code in BUILD_ERROR_KEYS else "incomplete", error.code, error.message)
        if validate_plan(plan):
            logger.warning("만든 일정이 검증을 통과하지 못했습니다: %s", ",".join(validate_plan(plan)))
            return self._fail("plan_invalid", "plan_invalid", "The generated plan failed validation.")
        self.plan, self.notice = plan, None
        return {
            "plan_id": plan.plan_id,
            "date": plan.date.isoformat(),
            "stops": [
                {
                    "stop_id": s.stop_id,
                    "place_id": s.place_id,
                    "name": place_name(places[s.place_id], self.profile.language),
                    "start": s.start.isoformat(),
                    "end": s.end.isoformat(),
                }
                for s in plan.stops
            ],
        }
