"""보전 지표(metrics.py, 스펙 작업 4) 테스트. sample_plan.json 4곳(자갈치 고정) 기준."""

import datetime as dt

from app.guardian.metrics import compute_metrics, total_travel_min
from guardian_fixtures import at, load_sample_plan, make_context

PLAN = load_sample_plan()
BEFORE = PLAN.stops  # s1 감천 · s2 자갈치(고정) · s3 부산타워 · s4 해운대
# 기본 이동 시간: 감천→자갈치 15, 자갈치→부산타워 10, 부산타워→해운대 40 (합 65)


def replace(stops, stop_id, **update):
    return [s.model_copy(update=update) if s.stop_id == stop_id else s for s in stops]


def test_total_travel():
    assert total_travel_min(BEFORE, make_context()) == 65
    assert total_travel_min(BEFORE[:1], make_context()) == 0
    assert total_travel_min(BEFORE, make_context(travel_min={})) is None


def test_no_change():
    m = compute_metrics(BEFORE, BEFORE, make_context())
    assert (m.changed, m.kept, m.extra_travel_min, m.locked_kept) == (0, 4, 0, True)


def test_move_time_counts_zero_changed():
    # 시각만 옮기면 "변경 0곳 · 시간만 조정" (데모 장면 5)
    shift = dt.timedelta(minutes=-30)
    after = replace(BEFORE, "s4", start=BEFORE[3].start + shift, end=BEFORE[3].end + shift)
    m = compute_metrics(BEFORE, after, make_context())
    assert (m.changed, m.kept, m.extra_travel_min, m.locked_kept) == (0, 4, 0, True)


def test_replace_counts_one_changed_and_extra_travel():
    # 해운대 → 신세계 센텀시티. 부산타워→신세계 45분이면 이동 +5분 (계약 예시와 같은 숫자)
    ctx = make_context(travel_min={
        ("gamcheon-village", "jagalchi-market"): 15,
        ("jagalchi-market", "busan-tower"): 10,
        ("busan-tower", "haeundae-beach"): 40,
        ("busan-tower", "shinsegae-centum-city"): 45,
    })
    after = replace(BEFORE, "s4", place_id="shinsegae-centum-city")
    m = compute_metrics(BEFORE, after, ctx)
    assert (m.changed, m.kept, m.extra_travel_min, m.locked_kept) == (1, 3, 5, True)


def test_extra_travel_can_be_negative():
    ctx = make_context(travel_min={
        ("gamcheon-village", "jagalchi-market"): 15,
        ("jagalchi-market", "busan-tower"): 10,
        ("busan-tower", "haeundae-beach"): 40,
        ("busan-tower", "gukje-market"): 5,
    })
    after = replace(BEFORE, "s4", place_id="gukje-market")
    assert compute_metrics(BEFORE, after, ctx).extra_travel_min == -35


def test_reorder_counts_zero_changed():
    # 부산타워와 해운대 순서 바꾸기: 장소는 그대로, 이동 경로만 달라짐
    ctx = make_context(travel_min={
        ("gamcheon-village", "jagalchi-market"): 15,
        ("jagalchi-market", "haeundae-beach"): 45,
        ("haeundae-beach", "busan-tower"): 40,
        ("jagalchi-market", "busan-tower"): 10,
        ("busan-tower", "haeundae-beach"): 40,
    })
    after = replace(
        replace(BEFORE, "s3", start=at(15, 30), end=at(16, 30)),
        "s4", start=at(13, 30), end=at(15),
    )
    m = compute_metrics(BEFORE, after, ctx)
    assert (m.changed, m.kept, m.locked_kept) == (0, 4, True)
    assert m.extra_travel_min == (15 + 45 + 40) - 65


def test_remove_counts_changed():
    after = [s for s in BEFORE if s.stop_id != "s1"]
    m = compute_metrics(BEFORE, after, make_context())
    assert (m.changed, m.kept, m.locked_kept) == (1, 3, True)
    assert m.extra_travel_min == (10 + 40) - 65


def test_locked_moved_breaks_locked_kept():
    after = replace(BEFORE, "s2", start=at(12, 30), end=at(13, 30))
    assert compute_metrics(BEFORE, after, make_context()).locked_kept is False


def test_locked_replaced_or_removed_breaks_locked_kept():
    swapped = replace(BEFORE, "s2", place_id="gukje-market")
    assert compute_metrics(BEFORE, swapped, make_context()).locked_kept is False
    removed = [s for s in BEFORE if s.stop_id != "s2"]
    assert compute_metrics(BEFORE, removed, make_context()).locked_kept is False


def test_unknown_travel_gives_zero_extra():
    after = replace(BEFORE, "s4", place_id="beomeosa-temple")  # 범어사 이동 시간 없음
    m = compute_metrics(BEFORE, after, make_context())
    assert (m.changed, m.kept, m.extra_travel_min) == (1, 3, 0)
