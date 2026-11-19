"""점검 규칙 4개(rules.py) 단위 테스트. sample_plan.json(11/21 토)과 guardian_fixtures 의 context 를 쓴다."""

import datetime as dt

import pytest

from app.guardian.context import Event, OpeningHours
from app.guardian.rules import check_closed, check_crowded, check_rain, check_tight_transfer
from guardian_fixtures import at, hourly_weather, load_sample_plan, make_context

PLAN = load_sample_plan()
S1, S2, S3, S4 = PLAN.stops  # 감천(실외) · 자갈치(실내, 고정) · 부산타워(실내) · 해운대(실외)


def on_day(stop, days: int):
    """같은 시각으로 날짜만 옮긴 Stop. 11/21(토) 기준 days 일 뒤."""
    shift = dt.timedelta(days=days)
    return stop.model_copy(update={"start": stop.start + shift, "end": stop.end + shift})


def at_time(stop, start: dt.datetime, end: dt.datetime):
    return stop.model_copy(update={"start": start, "end": end})


def festival(place_id: str, day: int = 21) -> Event:
    start = dt.datetime(2026, 11, day, 18, tzinfo=at(0).tzinfo)
    return Event(name="해운대 빛축제", start=start, end=start + dt.timedelta(hours=4), place_ids=[place_id])


# ---------- 혼잡 ----------

class TestCrowded:
    def test_weekday_rule_saturday_medium(self):
        issue = check_crowded(S1, make_context())
        assert issue.type == "crowded" and issue.severity == "medium"
        assert issue.issue_id == "s1-crowded"
        assert "요일 규칙" in issue.detail

    def test_weekday_rule_sunday_low(self):
        assert check_crowded(on_day(S1, 1), make_context()).severity == "low"

    @pytest.mark.parametrize("days", [2, 3, 4, 5, 6])  # 월~금
    def test_weekday_rule_weekdays_no_issue(self, days):
        assert check_crowded(on_day(S1, days), make_context()) is None

    @pytest.mark.parametrize("rate, severity", [(96, "high"), (95, "high"), (90, "medium"), (85, "medium"), (84, None)])
    def test_rate_on_saturday(self, rate, severity):
        issue = check_crowded(S4, make_context(crowd={"haeundae-beach": rate}))
        assert (issue.severity if issue else None) == severity

    def test_high_rate_on_weekday_is_medium(self):
        # 금요일(11/27)은 주말이 아니라 high 까지 올리지 않는다
        issue = check_crowded(on_day(S4, 6), make_context(crowd={"haeundae-beach": 98}))
        assert issue.severity == "medium"

    def test_no_data_skips(self):
        # 집중률도 없고 요일 규칙 대상도 아닌 장소
        assert check_crowded(S4, make_context(crowd={})) is None

    def test_event_raises_one_level(self):
        ctx = make_context(crowd={"haeundae-beach": 90}, events=[festival("haeundae-beach")])
        issue = check_crowded(S4, ctx)
        assert issue.severity == "high"
        assert "행사일 가중" in issue.detail

    def test_event_without_crowd_issue_is_low(self):
        ctx = make_context(crowd={"haeundae-beach": 50}, events=[festival("haeundae-beach")])
        assert check_crowded(S4, ctx).severity == "low"

    def test_event_on_other_day_or_place_ignored(self):
        ctx = make_context(events=[festival("haeundae-beach", day=28), festival("gwangalli-beach")])
        assert check_crowded(S4, ctx) is None


# ---------- 비 ----------

class TestRain:
    def test_outdoor_rain_high(self):
        # 15~18시 비, 해운대 15:30-17:00 → 체류 시간 전부 비
        issue = check_rain(S4, make_context(weather=hourly_weather(rain_hours=range(15, 18))))
        assert issue.severity == "high" and issue.issue_id == "s4-rain"
        assert "80%" in issue.detail and "실외" in issue.detail

    def test_indoor_no_issue(self):
        # 13~15시 비라도 부산타워는 실내
        assert check_rain(S3, make_context(weather=hourly_weather(rain_hours=range(13, 15)))) is None

    def test_rain_outside_stay_no_issue(self):
        # 13~15시 비, 해운대는 15:30부터 → 겹치지 않음 (데모 장면 5 의 해결 후 상태)
        assert check_rain(S4, make_context(weather=hourly_weather(rain_hours=range(13, 15)))) is None

    def test_partial_rain_medium(self):
        # 감천 10:00-11:30 중 11시 칸만 비 → 30/90분 = 33% < 50%
        issue = check_rain(S1, make_context(weather=hourly_weather(rain_hours=range(11, 12))))
        assert issue.severity == "medium"

    def test_high_pop_without_rain_medium(self):
        assert check_rain(S4, make_context(weather=hourly_weather(pop=70))).severity == "medium"

    def test_low_pop_no_issue(self):
        assert check_rain(S4, make_context(weather=hourly_weather(pop=59))) is None

    def test_no_forecast_skips(self):
        assert check_rain(S4, make_context(weather=None)) is None
        # 체류 시간대 예보 칸이 하나도 없을 때도 건너뛴다
        assert check_rain(at_time(S4, at(21), at(22)), make_context()) is None


# ---------- 휴무 ----------

class TestClosed:
    def test_closed_weekday_high(self):
        ctx = make_context(hours={"busan-tower": OpeningHours(closed_weekdays=[5])})
        issue = check_closed(S3, ctx)
        assert issue.severity == "high" and issue.issue_id == "s3-closed"
        assert "휴무일" in issue.detail

    def test_closed_date_high(self):
        ctx = make_context(hours={"busan-tower": OpeningHours(closed_dates=[dt.date(2026, 11, 21)])})
        assert check_closed(S3, ctx).severity == "high"

    @pytest.mark.parametrize("opens, closes", [(dt.time(14), dt.time(22)), (dt.time(9), dt.time(14))])
    def test_outside_opening_hours_high(self, opens, closes):
        # 부산타워 13:30-14:30: 14시 개장이면 이르고, 14시 폐장이면 늦다
        ctx = make_context(hours={"busan-tower": OpeningHours(opens=opens, closes=closes)})
        issue = check_closed(S3, ctx)
        assert issue.severity == "high" and "운영시간" in issue.detail

    def test_within_hours_no_issue(self):
        ctx = make_context(hours={"busan-tower": OpeningHours(opens=dt.time(10), closes=dt.time(22))})
        assert check_closed(S3, ctx) is None

    def test_no_hours_skips(self):
        assert check_closed(S3, make_context(hours={})) is None

    def test_locked_stop_still_reported(self):
        # 고정 일정도 점검한다. 심각도를 low 로 낮추는 일은 check_plan 이 한다
        ctx = make_context(hours={"jagalchi-market": OpeningHours(closed_weekdays=[5])})
        assert check_closed(S2, ctx).severity == "high"


# ---------- 빠듯한 이동 ----------

class TestTightTransfer:
    def test_late_high(self):
        # 부산타워 14:30 → 해운대 15:00 시작(간격 30분), 이동 40분
        stop = at_time(S4, at(15), at(16, 30))
        issue = check_tight_transfer(S3, stop, make_context())
        assert issue.severity == "high" and issue.stop_id == "s4"
        assert issue.issue_id == "s4-tight_transfer"
        assert "이동 40분" in issue.detail and "간격 30분" in issue.detail

    def test_small_buffer_medium(self):
        # 간격 45분, 이동 40분 → 여유 5분
        stop = at_time(S4, at(15, 15), at(16, 45))
        assert check_tight_transfer(S3, stop, make_context()).severity == "medium"

    def test_buffer_exactly_enough(self):
        # 간격 50분, 이동 40분 → 여유 10분 (기준 이상이면 문제 없음)
        stop = at_time(S4, at(15, 20), at(16, 50))
        assert check_tight_transfer(S3, stop, make_context()) is None

    def test_reverse_direction_travel_used(self):
        ctx = make_context(travel_min={("haeundae-beach", "busan-tower"): 40})
        stop = at_time(S4, at(15), at(16, 30))
        assert check_tight_transfer(S3, stop, ctx).severity == "high"

    def test_unknown_travel_skips(self):
        assert check_tight_transfer(S3, S4, make_context(travel_min={})) is None


def test_sample_plan_baseline():
    """기본 context 에서 sample_plan 에 남는 문제는 토요일 감천(요일 규칙) 하나뿐이다."""
    ctx = make_context()
    issues = [check_crowded(s, ctx) for s in PLAN.stops]
    issues += [check_rain(s, ctx) for s in PLAN.stops]
    issues += [check_closed(s, ctx) for s in PLAN.stops]
    issues += [check_tight_transfer(p, s, ctx) for p, s in zip(PLAN.stops, PLAN.stops[1:])]
    found = [i for i in issues if i]
    assert [(i.issue_id, i.severity) for i in found] == [("s1-crowded", "medium")]
