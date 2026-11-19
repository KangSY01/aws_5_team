"""문제 유형별 점검 규칙 4개. LLM 미사용, 순수 파이썬.

각 함수는 Stop 하나(또는 이웃한 두 Stop)를 보고 Issue 하나나 None 을 돌려준다.
필요한 데이터가 context 에 없으면 None 을 돌려 그 규칙만 건너뛴다.
고정 일정의 심각도 제한(low)과 정렬은 check_plan 이 한다.
"""

import datetime as dt

from app.guardian import thresholds as th
from app.guardian.context import CheckContext
from app.models.plan import Issue, IssueType, Severity, Stop

_LEVELS: tuple[Severity, ...] = ("low", "medium", "high")
_WEEKDAY_KO = "월화수목금토일"


def _issue(stop: Stop, type_: IssueType, severity: Severity, detail: str) -> Issue:
    # issue_id 는 같은 일정·같은 문제면 항상 같은 값이어야 한다
    return Issue(issue_id=f"{stop.stop_id}-{type_}", type=type_, stop_id=stop.stop_id, severity=severity, detail=detail)


def _raise_one(severity: Severity | None) -> Severity:
    """심각도를 한 단계 올린다. 문제가 없던 곳은 low 가 된다."""
    if severity is None:
        return "low"
    return _LEVELS[min(_LEVELS.index(severity) + 1, len(_LEVELS) - 1)]


def _minutes(delta: dt.timedelta) -> int:
    return int(delta.total_seconds() // 60)


def _hhmm(t: dt.datetime) -> str:
    return t.strftime("%H:%M")


# ---------- 혼잡 ----------

def _base_crowd(stop: Stop, ctx: CheckContext) -> tuple[Severity | None, str] | None:
    """행사 가중 전 혼잡 심각도와 근거. 판단할 데이터가 없으면 None."""
    weekday = stop.start.weekday()
    day = _WEEKDAY_KO[weekday]
    rate = ctx.crowd.get(stop.place_id)

    if rate is None:
        if stop.place_id not in th.WEEKDAY_RULE_PLACES:
            return None
        # 집중률에 없는 명소는 요일 규칙으로 대체한다 (평일 낮음, 토 가장 높음, 일 높음)
        return th.WEEKDAY_RULE_SEVERITY.get(weekday), f"{day}요일 요일 규칙, 집중률 데이터 없음"

    # 집중률은 이 장소 안에서의 상대값이다. 다른 장소 값과 비교하지 않는다
    detail = f"{day}요일 집중률 {rate:g}"
    if rate >= th.CROWD_HIGH_RATE and weekday >= 5:
        return "high", detail
    if rate >= th.CROWD_MEDIUM_RATE:
        return "medium", detail
    return None, detail


def _event_on(stop: Stop, ctx: CheckContext) -> str | None:
    """방문일에 이 장소(또는 근처)에서 열리는 대형 행사 이름."""
    day = stop.start.date()
    for event in ctx.events:
        if stop.place_id in event.place_ids and event.start.date() <= day <= event.end.date():
            return event.name
    return None


def check_crowded(stop: Stop, ctx: CheckContext) -> Issue | None:
    """방문일 혼잡. 집중률 기준 또는 요일 규칙으로 판단하고, 행사일이면 한 단계 올린다.

    집중률은 일 단위 값이라 시간대별 혼잡은 판단하지 않는다.
    """
    base = _base_crowd(stop, ctx)
    event = _event_on(stop, ctx)
    if base is None and event is None:
        return None

    severity, detail = base if base else (None, "혼잡 데이터 없음")
    if event:
        severity = _raise_one(severity)
        detail = f"{detail}, 행사일 가중({event})"
    if severity is None:
        return None
    return _issue(stop, "crowded", severity, detail)


# ---------- 비 ----------

def check_rain(stop: Stop, ctx: CheckContext) -> Issue | None:
    """실외 장소의 체류 시간대 비. 최대 강수확률과 강수가 있는 시간 비율로 판단한다.

    예보가 없거나(약 3일 이후) 체류 시간대 예보가 없으면 건너뛴다.
    """
    place = ctx.places.get(stop.place_id)
    if place is None or place.indoor or ctx.weather is None:
        return None

    hour = dt.timedelta(hours=1)
    stay_min = _minutes(stop.end - stop.start)
    max_pop = None
    wet_min = 0
    for slot in ctx.weather:
        # 예보 한 칸은 [time, time+1시간) 구간이다. 체류 시간과 겹치는 칸만 본다
        overlap = _minutes(min(stop.end, slot.time + hour) - max(stop.start, slot.time))
        if overlap <= 0:
            continue
        max_pop = slot.pop if max_pop is None else max(max_pop, slot.pop)
        if slot.has_precipitation:
            wet_min += overlap
    if max_pop is None or stay_min <= 0:
        return None

    ratio = wet_min / stay_min
    if ratio >= th.RAIN_PTY_HIGH_RATIO:
        severity: Severity = "high"
    elif max_pop >= th.RAIN_POP_MEDIUM or wet_min > 0:
        severity = "medium"
    else:
        return None
    detail = f"{_hhmm(stop.start)}-{_hhmm(stop.end)} 최대 강수확률 {max_pop}%, 강수 시간 {ratio:.0%}, 실외 장소"
    return _issue(stop, "rain", severity, detail)


# ---------- 휴무 ----------

def check_closed(stop: Stop, ctx: CheckContext) -> Issue | None:
    """휴무일이거나 체류 시간대가 운영시간 밖이면 high. 영업 정보가 없으면 건너뛴다."""
    hours = ctx.hours.get(stop.place_id)
    if hours is None:
        return None

    day = stop.start.date()
    if day in hours.closed_dates or day.weekday() in hours.closed_weekdays:
        return _issue(stop, "closed", "high", f"휴무일({_WEEKDAY_KO[day.weekday()]}요일 {day.isoformat()})")

    start, end = stop.start.time(), stop.end.time()
    if (hours.opens and start < hours.opens) or (hours.closes and end > hours.closes):
        opens = hours.opens.strftime("%H:%M") if hours.opens else "?"
        closes = hours.closes.strftime("%H:%M") if hours.closes else "?"
        detail = f"체류 {_hhmm(stop.start)}-{_hhmm(stop.end)}, 운영시간 {opens}-{closes} 밖"
        return _issue(stop, "closed", "high", detail)
    return None


# ---------- 빠듯한 이동 ----------

def check_tight_transfer(prev: Stop, stop: Stop, ctx: CheckContext) -> Issue | None:
    """이전 Stop 끝 + 이동 시간 + 여유가 다음 Stop 시작보다 늦으면 Issue. Issue 는 다음 Stop 에 단다.

    여유가 TRANSFER_BUFFER_MIN 미만이면 medium, 0 미만(제시간에 못 감)이면 high.
    이동 시간을 모르면 건너뛴다.
    """
    travel = ctx.travel(prev.place_id, stop.place_id)
    if travel is None:
        return None

    gap = _minutes(stop.start - prev.end)
    slack = gap - travel
    if slack >= th.TRANSFER_BUFFER_MIN:
        return None
    severity: Severity = "high" if slack < 0 else "medium"
    detail = f"이동 {travel}분, 간격 {gap}분, 여유 {slack}분"
    return _issue(stop, "tight_transfer", severity, detail)
