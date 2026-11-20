"""Guardian 통합·데모 테스트 (스펙 작업 7).

- design.md 「테스트」 표의 케이스 전부
- docs/demo-readiness.md 의 Guardian 장면(1·2·5·6)과 /plan/check 응답 조립 흐름
sample_plan.json(11/21 토, 4곳, 자갈치 고정)과 places.json 에 있는 장소만 쓴다. 수치는 테스트용 값이다.
"""

import datetime as dt

from app.guardian.check import check_plan
from app.guardian.context import Event, OpeningHours
from app.guardian.delay import propose_delay_repairs
from app.guardian.repair import apply_option, new_places, propose_repairs
from app.models.api import CheckResponse
from app.models.plan import RepairOption
from guardian_fixtures import BASE_CROWD, BASE_TRAVEL_MIN, at, hourly_weather, load_sample_plan, make_context

PLAN = load_sample_plan()  # s1 감천 10:00-11:30 · s2 자갈치(고정) 12:00-13:00 · s3 부산타워 13:30-14:30 · s4 해운대 15:30-17:00
LOCKED = PLAN.stops[1]


def issue_map(plan, ctx):
    return {i.issue_id: i for i in check_plan(plan, ctx)}


def summary(options: list[RepairOption]) -> list[tuple[str, int, int]]:
    """(action, changed, extra_travel_min)."""
    return [(o.action, o.metrics.changed, o.metrics.extra_travel_min) for o in options]


def place_of(option: RepairOption, stop_id: str) -> str | None:
    change = next(c for c in option.changes if c.stop_id == stop_id)
    return change.after.place_id if change.after else None


def assert_locked_kept(option: RepairOption, plan=PLAN, locked_id: str = LOCKED.stop_id) -> None:
    before = next(s for s in plan.stops if s.stop_id == locked_id)
    after = next(s for s in apply_option(plan, option).stops if s.stop_id == locked_id)
    assert option.metrics.locked_kept is True
    assert (after.place_id, after.start, after.end) == (before.place_id, before.start, before.end)


# ---------- design.md 「테스트」 표 ----------

def test_table_saturday_gamcheon_weekday_rule():
    issue = issue_map(PLAN, make_context())["s1-crowded"]
    assert issue.severity == "medium"
    assert "요일 규칙" in issue.detail


def test_table_rain_15_18_haeundae_first_repair_indoor_replace():
    ctx = make_context(
        weather=hourly_weather(rain_hours=range(15, 18)),
        travel_min=BASE_TRAVEL_MIN | {("busan-tower", "shinsegae-centum-city"): 45},
    )
    issue = issue_map(PLAN, ctx)["s4-rain"]
    assert issue.severity == "high"

    first = propose_repairs(PLAN, issue, ctx)[0]
    assert first.action == "replace"
    assert ctx.places[place_of(first, "s4")].indoor is True
    assert first.metrics.locked_kept is True


def test_table_rain_13_15_indoor_busan_tower_has_no_issue():
    ctx = make_context(weather=hourly_weather(rain_hours=range(13, 15)))
    assert not any(i.stop_id == "s3" for i in check_plan(PLAN, ctx))


def test_table_locked_jagalchi_closed_is_low_without_repairs():
    ctx = make_context(hours={"jagalchi-market": OpeningHours(closed_weekdays=[5])})
    issue = issue_map(PLAN, ctx)["s2-closed"]
    assert issue.severity == "low"
    assert propose_repairs(PLAN, issue, ctx) == []


def test_table_travel_40_gap_30_is_tight_transfer_high():
    # 자갈치 13:00 → 부산타워 13:30 (간격 30분), 이동 40분
    ctx = make_context(travel_min=BASE_TRAVEL_MIN | {("jagalchi-market", "busan-tower"): 40})
    assert issue_map(PLAN, ctx)["s3-tight_transfer"].severity == "high"


def test_table_same_input_gives_same_issue_ids():
    ctx = make_context(weather=hourly_weather(rain_hours=range(15, 18)))
    assert [i.issue_id for i in check_plan(PLAN, ctx)] == [i.issue_id for i in check_plan(PLAN, ctx)]


def test_table_every_repair_keeps_jagalchi():
    contexts = [
        make_context(),
        make_context(weather=hourly_weather(rain_hours=range(15, 18)),
                     travel_min=BASE_TRAVEL_MIN | {("busan-tower", "shinsegae-centum-city"): 45}),
        make_context(hours={"busan-tower": OpeningHours(opens=dt.time(14))}),
        make_context(travel_min=BASE_TRAVEL_MIN | {("jagalchi-market", "busan-tower"): 40}),
    ]
    count = 0
    for ctx in contexts:
        for issue in check_plan(PLAN, ctx):
            for option in propose_repairs(PLAN, issue, ctx):
                assert_locked_kept(option)
                count += 1
    assert count > 0


# ---------- 데모 장면 (docs/demo-readiness.md) ----------

# 장면 1·2: 해운대 빛축제(행사, 장소 haeundae-beach). 해운대 집중률 90 → 토요일 medium, 행사일 가중으로 high(🔴)
FESTIVAL = Event(name="해운대 빛축제", start=at(18), end=at(22), place_ids=["haeundae-beach"])
SCENE_1_CTX = make_context(
    crowd=BASE_CROWD | {"haeundae-beach": 90.0},
    events=[FESTIVAL],
    travel_min=BASE_TRAVEL_MIN | {("busan-tower", "gwangalli-beach"): 30},
)


def test_scene_1_festival_day_crowded_badge():
    issues = check_plan(PLAN, SCENE_1_CTX)
    haeundae = next(i for i in issues if i.issue_id == "s4-crowded")
    assert haeundae.severity == "high"
    assert "행사일 가중" in haeundae.detail
    assert issues[0].issue_id == "s4-crowded"  # high 가 맨 앞 (배지 우선순위)
    # 고정 일정(자갈치)에는 high 배지가 없다
    assert all(i.severity == "low" for i in issues if i.stop_id == LOCKED.stop_id)


def test_scene_2_badge_tap_replaces_with_similar_beach():
    # 행사는 18시 이후라 15:30 체류와 겹치지 않는다 → 시간 이동 근거 없음 → 같은 beach 로 교체
    issue = issue_map(PLAN, SCENE_1_CTX)["s4-crowded"]
    options = propose_repairs(PLAN, issue, SCENE_1_CTX)

    assert summary(options) == [("replace", 1, -10)]
    assert place_of(options[0], "s4") == "gwangalli-beach"
    m = options[0].metrics
    assert (m.kept, m.locked_kept) == (3, True)  # "변경 1곳 · 3곳 유지"
    # 바꾸기를 적용하면 해운대 혼잡 배지가 사라진다
    assert "s4-crowded" not in issue_map(apply_option(PLAN, options[0]), SCENE_1_CTX)


def test_scene_5_afternoon_rain_moves_time_first():
    # 해운대 체류 시간대(15~17시) 비. 첫 안은 시간만 옮기기(변경 0곳), 다음 안은 실내 교체(변경 1곳)
    ctx = make_context(
        weather=hourly_weather(rain_hours=range(15, 17)),
        travel_min=BASE_TRAVEL_MIN | {("busan-tower", "shinsegae-centum-city"): 45},
    )
    options = propose_repairs(PLAN, issue_map(PLAN, ctx)["s4-rain"], ctx)

    assert summary(options) == [("move_time", 0, 0), ("replace", 1, 5)]
    assert place_of(options[0], "s4") == "haeundae-beach"
    assert ctx.places[place_of(options[1], "s4")].indoor is True
    for option in options:
        assert_locked_kept(option)


def test_scene_6_late_30_min_keeps_locked_stop():
    # 해운대를 고정(빛축제 자리)하고 13:40 에 30분 지연.
    # 첫 안: 부산타워 14:00 시작, 체류를 50분으로 줄여 해운대 15:30 유지(변경 0곳). 다음 안: 부산타워 빼기(변경 1곳)
    plan = PLAN.model_copy(update={"stops": [
        s.model_copy(update={"locked": s.stop_id in ("s2", "s4")}) for s in PLAN.stops
    ]})
    ctx = make_context(now=at(13, 40), travel_min=BASE_TRAVEL_MIN | {
        ("busan-tower", "haeundae-beach"): 30,
        ("jagalchi-market", "haeundae-beach"): 20,
    })
    options = propose_delay_repairs(plan, 30, ctx)

    assert summary(options) == [("move_time", 0, 0), ("remove", 1, -20)]
    s3 = next(c.after for c in options[0].changes if c.stop_id == "s3")
    assert (s3.start, s3.end) == (at(14), at(14, 50))
    for option in options:
        assert_locked_kept(option, plan, "s4")
        assert_locked_kept(option, plan, "s2")


def test_scene_1_2_check_response_matches_contract_models():
    # handler.py 연결(스펙 작업 9) 전에, /plan/check 응답을 Guardian 결과로 조립해 계약 모델에 맞는지 확인
    issues = check_plan(PLAN, SCENE_1_CTX)
    repairs = {i.issue_id: propose_repairs(PLAN, i, SCENE_1_CTX) for i in issues}
    places = new_places(PLAN, [o for options in repairs.values() for o in options], SCENE_1_CTX)
    response = CheckResponse(
        plan_id=PLAN.plan_id, checked_at=SCENE_1_CTX.now, issues=issues, repairs=repairs, places=places,
    )

    data = CheckResponse.model_validate_json(response.model_dump_json())
    assert set(data.repairs) == {i.issue_id for i in data.issues}
    assert [o.action for o in data.repairs["s4-crowded"]] == ["replace"]
    assert [o.action for o in data.repairs["s1-crowded"]] == ["remove"]  # 계약 예시와 같은 경우
    assert [p.place_id for p in data.places] == ["gwangalli-beach"]
    assert all(p.place_id in SCENE_1_CTX.places for p in data.places)
