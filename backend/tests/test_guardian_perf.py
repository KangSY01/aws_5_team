"""성능 확인 (스펙 작업 10, 요구사항 6.1·6.2).

- check_plan: Stop 5곳 기준 300ms 이내
- propose_repairs: Issue 하나, Stop 5곳 기준 1초 이내
외부 데이터는 미리 조립한 context 로 넘긴다. 교체 후보를 모두 평가하도록 places.json 32곳 전체에 이동 시간을 넣은
나쁜 경우로 잰다. 수치는 테스트용 값이다.

    uv run pytest -q tests/test_guardian_perf.py -s   # 측정값 출력
"""

import itertools
import statistics
import time

from app.guardian.check import check_plan
from app.guardian.context import Event
from app.guardian.delay import propose_delay_repairs
from app.guardian.repair import propose_repairs
from app.models.plan import Stop
from guardian_fixtures import BASE_CROWD, at, hourly_weather, load_places, load_sample_plan, make_context

CHECK_LIMIT_SEC = 0.3
REPAIR_LIMIT_SEC = 1.0
RUNS = 5

BASE = load_sample_plan()
PLAN = BASE.model_copy(update={"stops": BASE.stops + [
    Stop(stop_id="s5", place_id="gwangalli-beach", start=at(17, 40), end=at(19)),
]})  # 감천 · 자갈치(고정) · 부산타워 · 해운대 · 광안리


def worst_case_context():
    """문제가 여러 개 나고, 모든 장소 쌍의 이동 시간을 알아 교체 후보를 전부 평가하는 context."""
    places = load_places()
    travel = {(a, b): 20 for a, b in itertools.combinations(sorted(places), 2)}
    return make_context(
        weather=hourly_weather(rain_hours=range(15, 19)),
        crowd=BASE_CROWD | {"haeundae-beach": 99.0},
        events=[Event(name="테스트 행사", start=at(16), end=at(21), place_ids=["haeundae-beach", "gwangalli-beach"])],
        travel_min=travel,
    )


def timed(func, *args) -> float:
    """RUNS 번 실행한 중앙값(초)."""
    samples = []
    for _ in range(RUNS):
        start = time.perf_counter()
        func(*args)
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def test_check_plan_within_300ms():
    ctx = worst_case_context()
    assert len(check_plan(PLAN, ctx)) >= 3  # 비·혼잡·이동 등 여러 문제가 나는 상황인지 확인
    elapsed = timed(check_plan, PLAN, ctx)
    print(f"\ncheck_plan: {elapsed * 1000:.1f}ms (Stop {len(PLAN.stops)}곳)")
    assert elapsed < CHECK_LIMIT_SEC


def test_propose_repairs_within_1s_per_issue():
    ctx = worst_case_context()
    issues = check_plan(PLAN, ctx)
    worst = 0.0
    for issue in issues:
        elapsed = timed(propose_repairs, PLAN, issue, ctx)
        print(f"\npropose_repairs {issue.issue_id}: {elapsed * 1000:.1f}ms")
        worst = max(worst, elapsed)
    assert worst < REPAIR_LIMIT_SEC


def test_propose_delay_repairs_within_1s():
    # 요구사항 6 에 지연 재조정 기준은 없다. propose_repairs 와 같은 1초로 확인한다
    ctx = worst_case_context().model_copy(update={"now": at(13, 40)})
    elapsed = timed(propose_delay_repairs, PLAN, 60, ctx)
    print(f"\npropose_delay_repairs(60분): {elapsed * 1000:.1f}ms")
    assert elapsed < REPAIR_LIMIT_SEC
