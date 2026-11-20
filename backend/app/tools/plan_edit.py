"""일정 부분 수정 도구 (에이전트 담당). 작업 3.

일정은 전체를 다시 만들지 않고 이 도구들로만 고친다.

현재 일정을 도구에 넘기는 방법: 요청마다 PlanEditor 를 하나 만들고, 그 인스턴스의 메서드를 Strands 도구로 쓴다
(Strands 클래스 기반 도구). 일정은 인스턴스에만 있으므로 요청 사이에 공유되지 않고, 도구 인자는 LLM 이 정할 값
(stop_id, place_id, 시각)만 남는다.

    editor = PlanEditor(plan)                       # run_chat 이 요청마다 만든다
    agent = Agent(model=..., tools=[*lookup_tools, *editor.tools])
    editor.allow_search_results(search_places_result)  # search_places 결과가 나올 때마다 알려 준다
    plan_changes = editor.net_changes()             # 응답의 plan_changes

장소 ID 검증은 두 겹이다. (1) known_place_ids 에 없으면 거부(기본은 places.json). (2) 같은 요청에서
search_places 가 돌려준 적이 없으면 거부. plan_edit 은 lookup.py 를 가져오지 않는다. 조회 도구가 바뀌어도
run_chat 이 그 결과를 allow_search_results 로 넘기면 된다.
"""

import json
import logging
import re
from collections.abc import Callable, Collection, Iterable
from pathlib import Path
from typing import Any

from pydantic import AwareDatetime, TypeAdapter, ValidationError
from strands import tool

from app.models.plan import Plan, Stop, StopChange

logger = logging.getLogger(__name__)

_PLACES_PATH = Path(__file__).parent.parent / "data" / "places.json"
_AWARE_DATETIME = TypeAdapter(AwareDatetime)
_STOP_ID_NUMBER = re.compile(r"^s(\d+)$")


class PlanEditError(Exception):
    """도구가 일정을 바꾸지 않고 오류 dict 로 돌려줄 사유."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def load_known_place_ids() -> frozenset[str]:
    """backend/app/data/places.json 의 장소 ID. 데이터 담당이 출처를 바꾸면 PlanEditor 에 직접 넘긴다."""
    places = json.loads(_PLACES_PATH.read_text(encoding="utf-8"))
    return frozenset(place["place_id"] for place in places)


def _error_dict(error: PlanEditError) -> dict:
    return {"error": {"code": error.code, "message": error.message}}


def _parse_time(name: str, value: Any) -> AwareDatetime:
    if not isinstance(value, str):
        raise PlanEditError("invalid_time", f"{name} must be an ISO 8601 string with a timezone offset.")
    try:
        return _AWARE_DATETIME.validate_python(value)
    except ValidationError:
        raise PlanEditError(
            "invalid_time",
            f"{name} must be ISO 8601 with a timezone offset, e.g. 2026-11-21T10:00:00+09:00.",
        )


def _parse_range(start: Any, end: Any) -> tuple[AwareDatetime, AwareDatetime]:
    start_at, end_at = _parse_time("start", start), _parse_time("end", end)
    if start_at >= end_at:
        raise PlanEditError("invalid_time", "start must be earlier than end.")
    return start_at, end_at


class PlanEditor:
    """요청 한 건 범위의 일정 편집 상태와 부분 수정 도구 4개.

    plan 은 복사해서 쓰므로 호출자의 Plan 은 바뀌지 않는다. 요청 시작 시점의 일정은 따로 보관해
    net_changes() 의 before 기준과 locked 검증 기준으로 쓴다.
    """

    def __init__(self, plan: Plan, known_place_ids: Collection[str] | None = None):
        self._original = plan.model_copy(deep=True)  # 요청 시작 시점. 바꾸지 않는다
        self._plan = plan.model_copy(deep=True)  # 도구가 고치는 작업본
        self._known = frozenset(known_place_ids) if known_place_ids is not None else load_known_place_ids()
        self._candidates: set[str] = set()  # 이 요청에서 search_places 가 돌려준 장소 ID

    # ---- 일정 상태 ----

    @property
    def current_plan(self) -> Plan:
        """지금까지 수정을 반영한 일정 (복사본)."""
        return self._plan.model_copy(deep=True)

    def net_changes(self) -> list[StopChange]:
        """요청 시작 시점 대비 실제로 바뀐 Stop 만 StopChange 로 돌려준다 (ChatResponse.plan_changes).

        같은 Stop 을 여러 번 고쳤으면 처음 before 와 마지막 after 로 합쳐지고, 원래대로 돌아왔거나
        추가 후 제거한 Stop 은 빠진다.
        """
        now = {stop.stop_id: stop for stop in self._plan.stops}
        before_ids = {stop.stop_id for stop in self._original.stops}
        changes = [
            StopChange(stop_id=stop.stop_id, before=stop.model_copy(deep=True), after=_copy(now.get(stop.stop_id)))
            for stop in self._original.stops
            if now.get(stop.stop_id) != stop
        ]
        changes += [
            StopChange(stop_id=stop.stop_id, before=None, after=stop.model_copy(deep=True))
            for stop in self._plan.stops
            if stop.stop_id not in before_ids
        ]
        return changes

    # ---- 장소 후보 (조회 도구와의 접점) ----

    def allow_places(self, place_ids: Iterable[str]) -> None:
        """이 요청에서 조회 도구가 돌려준 장소 ID 를 교체·추가 후보로 등록한다."""
        self._candidates.update(place_ids)

    def allow_search_results(self, result: Any) -> None:
        """search_places 결과(Place dict 목록)에서 place_id 를 후보로 등록한다. 오류 dict 나 이상한 항목은 무시한다."""
        if not isinstance(result, list):
            return
        self.allow_places(
            item["place_id"] for item in result if isinstance(item, dict) and isinstance(item.get("place_id"), str)
        )

    # ---- 도구 ----

    @property
    def tools(self) -> list:
        """Agent(tools=...) 에 넘길 부분 수정 도구."""
        return [self.replace_stop, self.add_stop, self.remove_stop, self.move_stop]

    @tool
    def replace_stop(self, stop_id: str, new_place_id: str) -> dict:
        """Replace the place of one stop in the current plan. The stop's start and end times stay the same.

        Use this when the user wants a different place for an existing stop (for example an indoor place
        because of rain, or a less crowded one). Prefer this over rebuilding the plan. Never use it on a stop
        whose locked flag is true.

        Args:
            stop_id: ID of the stop to change, taken from CURRENT_PLAN (for example "s4").
            new_place_id: place_id of the new place. It must come from a search_places result in this conversation turn.

        Returns:
            On success, a StopChange dict: {"stop_id", "before", "after"} where before and after are the stop
            before and after the change. On failure, {"error": {"code", "message"}} and the plan is not changed.
            Error codes: stop_not_found, stop_locked, unknown_place, place_not_searched, no_change.
        """
        return self._run("replace_stop", lambda: self._replace(stop_id, new_place_id))

    @tool
    def add_stop(self, place_id: str, start: str, end: str) -> dict:
        """Add a new stop to the current plan.

        Use this only when the user explicitly asks to add a place. Do not use it to fix a problem with an
        existing stop (use replace_stop, move_stop or remove_stop for that).

        Args:
            place_id: place_id of the place to add. It must come from a search_places result in this conversation turn.
            start: Start time as ISO 8601 with timezone offset, for example "2026-11-21T16:00:00+09:00".
            end: End time in the same format. It must be later than start.

        Returns:
            On success, a StopChange dict with before = null and after = the new stop (its stop_id is assigned
            automatically and it is not locked). On failure, {"error": {"code", "message"}} and the plan is not
            changed. Error codes: unknown_place, place_not_searched, invalid_time.
        """
        return self._run("add_stop", lambda: self._add(place_id, start, end))

    @tool
    def remove_stop(self, stop_id: str) -> dict:
        """Remove one stop from the current plan.

        Use this when the user asks to drop a place, or when no good replacement exists. Never use it on a stop
        whose locked flag is true.

        Args:
            stop_id: ID of the stop to remove, taken from CURRENT_PLAN.

        Returns:
            On success, a StopChange dict with after = null. On failure, {"error": {"code", "message"}} and the plan
            is not changed. Error codes: stop_not_found, stop_locked.
        """
        return self._run("remove_stop", lambda: self._remove(stop_id))

    @tool
    def move_stop(self, stop_id: str, start: str, end: str) -> dict:
        """Move one stop to a different time. The place stays the same.

        Use this when a stop only needs a different time, for example to avoid a crowded hour or to fix a tight
        transfer. Never use it on a stop whose locked flag is true.

        Args:
            stop_id: ID of the stop to move, taken from CURRENT_PLAN.
            start: New start time as ISO 8601 with timezone offset, for example "2026-11-21T09:00:00+09:00".
            end: New end time in the same format. It must be later than start.

        Returns:
            On success, a StopChange dict {"stop_id", "before", "after"}. On failure, {"error": {"code", "message"}}
            and the plan is not changed. Error codes: stop_not_found, stop_locked, invalid_time, no_change.
        """
        return self._run("move_stop", lambda: self._move(stop_id, start, end))

    # ---- 구현 ----

    def _run(self, tool_name: str, action: Callable[[], StopChange]) -> dict:
        try:
            return action().model_dump(mode="json")
        except PlanEditError as error:
            logger.warning("일정 수정 거부: 도구=%s 사유=%s", tool_name, error.code)
            return _error_dict(error)

    def _find(self, stop_id: str) -> tuple[int, Stop]:
        for index, stop in enumerate(self._plan.stops):
            if stop.stop_id == stop_id:
                return index, stop
        raise PlanEditError("stop_not_found", f"No stop with stop_id {stop_id!r} in the current plan.")

    def _find_unlocked(self, stop_id: str) -> tuple[int, Stop]:
        index, stop = self._find(stop_id)
        if stop.locked:
            raise PlanEditError(
                "stop_locked",
                f"Stop {stop_id!r} is locked and must not be changed. "
                "Tell the user to unlock it in the app first if they want to change it.",
            )
        return index, stop

    def _require_place(self, place_id: str) -> None:
        if place_id not in self._known:
            raise PlanEditError("unknown_place", f"place_id {place_id!r} does not exist.")
        if place_id not in self._candidates:
            raise PlanEditError(
                "place_not_searched",
                f"place_id {place_id!r} was not returned by search_places in this turn. "
                "Call search_places and use a place_id from its result.",
            )

    def _replace(self, stop_id: str, new_place_id: str) -> StopChange:
        index, stop = self._find_unlocked(stop_id)
        self._require_place(new_place_id)
        if stop.place_id == new_place_id:
            raise PlanEditError("no_change", f"Stop {stop_id!r} is already at {new_place_id!r}.")
        after = stop.model_copy(update={"place_id": new_place_id})
        self._plan.stops[index] = after
        return StopChange(stop_id=stop_id, before=stop, after=after)

    def _add(self, place_id: str, start: str, end: str) -> StopChange:
        self._require_place(place_id)
        start_at, end_at = _parse_range(start, end)
        stop = Stop(stop_id=self._next_stop_id(), place_id=place_id, start=start_at, end=end_at, locked=False)
        self._plan.stops.append(stop)
        self._sort_stops()
        return StopChange(stop_id=stop.stop_id, before=None, after=stop)

    def _remove(self, stop_id: str) -> StopChange:
        index, stop = self._find_unlocked(stop_id)
        del self._plan.stops[index]
        return StopChange(stop_id=stop_id, before=stop, after=None)

    def _move(self, stop_id: str, start: str, end: str) -> StopChange:
        index, stop = self._find_unlocked(stop_id)
        start_at, end_at = _parse_range(start, end)
        if (stop.start, stop.end) == (start_at, end_at):
            raise PlanEditError("no_change", f"Stop {stop_id!r} already has that start and end.")
        after = stop.model_copy(update={"start": start_at, "end": end_at})
        self._plan.stops[index] = after
        self._sort_stops()
        return StopChange(stop_id=stop_id, before=stop, after=after)

    def _next_stop_id(self) -> str:
        """s<번호> 형식의 새 ID. 요청 중 제거한 Stop 의 ID 도 다시 쓰지 않는다."""
        used = {s.stop_id for s in self._original.stops} | {s.stop_id for s in self._plan.stops}
        numbers = [int(m.group(1)) for stop_id in used if (m := _STOP_ID_NUMBER.match(stop_id))]
        return f"s{max(numbers, default=0) + 1}"

    def _sort_stops(self) -> None:
        """시작 시각순 유지 (Guardian 도 시각순으로 읽는다). 같은 시각이면 기존 순서를 지킨다."""
        self._plan.stops.sort(key=lambda stop: stop.start)


def _copy(stop: Stop | None) -> Stop | None:
    return stop.model_copy(deep=True) if stop is not None else None
