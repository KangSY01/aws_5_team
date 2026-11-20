"""search_places 결과를 D 의 rank_places 로 다시 정렬하고, 점수 근거를 붙여 모델에 넘긴다 (A). LLM 을 부르지 않는다.

흐름: 모델이 search_places 호출 → B 의 결과(Place dict 목록) → 이 훅이
  1) 결과의 place_id 중 places.json 에 있는 것만 후보로 삼고
  2) 후보를 담은 임시 일정으로 Guardian 의 build_context 를 만들어 (집중률·운영시간·행사만 조회)
  3) rank_places(후보, profile, ctx, day=방문일, limit=5) 로 채점해
  4) 상위 장소를 순위대로 앞에 두고 각 항목에 "ranking": {rank, total, breakdown, notes} 를 붙인다.
     나머지 장소는 원래 순서대로 뒤에 둔다 (빼지 않는다. 일정 후보 허용 범위와 장소 ID 검증은 그대로다).
- rank_places 가 예외를 던지거나 빈 목록을 돌려주면 결과를 바꾸지 않는다 (기존 방식).
- 체류 시간대와 앞 장소를 모르는 검색 단계라 start·end·prev_place_id 는 넘기지 않는다. 그래서 날씨·이동 항목은
  rank_places 가 중립값으로 두고, 그 조회(get_weather, get_travel_time)도 하지 않는다.
- API 응답(ChatResponse)에는 점수를 넣지 않는다. 모델이 읽는 도구 결과에만 들어간다.
"""

import datetime as dt
import json
import logging
from types import SimpleNamespace
from typing import Any

from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry

from app.chat.plan_rules import load_places
from app.guardian.context import KST, build_context
from app.models.plan import Plan, Profile, Stop
from app.ranking import rank_places

logger = logging.getLogger(__name__)

RANK_LIMIT = 5  # rank_places 기본값과 같다
TOOL_NAME = "search_places"
# 모델이 읽는 설명 (영어, tech.md). 점수의 뜻과 쓰는 법만 적는다
RANKING_NOTE = (
    "Rule-based fit score for this user's profile and visit day (0-100, higher is better). breakdown items are 0-1 "
    "(interest, crowd, travel, weather, foreigner, dispersal); notes are reason codes. Prefer higher-ranked places "
    "and use breakdown/notes to explain why. It is not a rating or popularity."
)


def _lookups() -> SimpleNamespace:
    """build_context 에 넘길 조회 도구 묶음. 검색 단계 채점에 쓰는 집중률·운영시간·행사만 둔다 (모두 app/data 파일)."""
    from app.tools import lookup

    return SimpleNamespace(get_crowd=lookup.get_crowd, get_hours=lookup.get_hours, get_events=lookup.get_events)


def _probe_plan(place_ids: list[str], profile: Profile, day: dt.date) -> Plan:
    """후보 장소의 정보를 build_context 로 모으기 위한 임시 일정. 저장하지 않고, 시각은 의미가 없다."""
    base = dt.datetime.combine(day, dt.time(9, 0), KST)
    stops = [
        Stop(stop_id=f"rank-{i}", place_id=pid, start=base + dt.timedelta(minutes=i), end=base + dt.timedelta(minutes=i + 1))
        for i, pid in enumerate(place_ids)
    ]
    return Plan(plan_id="rank-probe", date=day, profile=profile, stops=stops)


def rank_search_results(results: Any, profile: Profile, day: dt.date, demo_now: dt.datetime | None = None,
                        ranker=rank_places, lookups: Any = None) -> list | None:
    """search_places 결과를 순위대로 바꾼 새 목록. 바꿀 것이 없거나 실패하면 None (호출한 쪽은 원래 결과를 쓴다)."""
    if not isinstance(results, list):
        return None
    known = load_places()
    candidates = list(dict.fromkeys(
        item["place_id"] for item in results
        if isinstance(item, dict) and isinstance(item.get("place_id"), str) and item["place_id"] in known
    ))
    if not candidates:
        return None
    ctx = build_context(_probe_plan(candidates, profile, day), demo_now=demo_now,
                        lookups=lookups if lookups is not None else _lookups())
    ranked = ranker(candidates, profile, ctx, day=day, limit=RANK_LIMIT)
    ranked = [s for s in ranked or [] if getattr(s, "place_id", None) in candidates]  # 후보 밖 ID 는 쓰지 않는다
    if not ranked:
        return None

    by_id = {item["place_id"]: item for item in results if isinstance(item, dict) and item.get("place_id") in candidates}
    top = []
    for rank, score in enumerate(ranked, start=1):
        top.append({**by_id[score.place_id], "ranking": {
            "rank": rank, "total": score.total, "breakdown": dict(score.breakdown), "notes": list(score.notes),
            "about": RANKING_NOTE,
        }})
    chosen = {s.place_id for s in ranked}
    rest = [item for item in results if not (isinstance(item, dict) and item.get("place_id") in chosen)]
    return top + rest


def _replace_payload(result: dict, data: list) -> dict:
    """ToolResult 의 내용을 data 로 바꾼 사본. 원래 형식(json 또는 text)을 따른다."""
    content = result.get("content") or []
    if content and "json" in content[0]:
        new_item = {"json": data}
    else:
        new_item = {"text": json.dumps(data, ensure_ascii=False)}
    return {**result, "content": [new_item]}


class PlaceRanker(HookProvider):
    """search_places 가 끝난 직후 결과를 순위대로 바꾼다. ToolRecorder 보다 먼저 돌아야 기록·후보도 같은 결과를 본다.

    Strands 는 AfterToolCallEvent 콜백을 등록 역순으로 부르므로, Agent 의 hooks 목록에서 ToolRecorder 뒤에 둔다.
    """

    def __init__(self, profile: Profile, day: dt.date, demo_now: dt.datetime | None = None):
        self.profile, self.day, self.demo_now = profile, day, demo_now
        self.applied = 0  # 순위를 반영한 횟수 (로그·테스트용)

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        registry.add_callback(AfterToolCallEvent, self._after)

    def _after(self, event: AfterToolCallEvent) -> None:
        if event.tool_use.get("name") != TOOL_NAME or not isinstance(event.result, dict):
            return
        if event.result.get("status") != "success":
            return
        try:
            from app.chat.tools import _payload

            ranked = rank_search_results(_payload(event.result), self.profile, self.day, self.demo_now)
        except Exception as error:  # 순위 평가가 실패해도 대화는 원래 검색 결과로 계속한다
            logger.warning("장소 순위 평가 실패, 원래 검색 결과를 씁니다: %s", type(error).__name__)
            return
        if ranked is None:
            return
        event.result = _replace_payload(event.result, ranked)
        self.applied += 1
        logger.info("장소 순위 반영: 상위 %d곳", sum(1 for item in ranked if isinstance(item, dict) and "ranking" in item))
