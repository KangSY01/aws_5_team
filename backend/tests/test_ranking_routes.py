"""귀가 경로 점수 (app/ranking/routes.py, 장면 7) 테스트."""

from app.ranking import rank_routes, score_route
from app.ranking import weights as w
from app.tools.return_options import return_options

BASELINE = {"depart_at": "2026-11-28T23:00:00+09:00", "station": "Haeundae", "congested": True, "minutes": 39,
            "mode": "subway"}


def opt(kind, depart, station="Haeundae", walk=0, extra=0, avoids=True, warnings=()):
    return {"type": kind, "depart_at": f"2026-11-{depart}+09:00", "station": station, "walk_min": walk,
            "extra_min": extra, "avoids_congestion": avoids, "warnings": list(warnings)}


EARLIER = opt("shift_earlier", "28T22:20:00", warnings=["leaves_before_event_end"])
LATER = opt("shift_later", "29T00:00:00", warnings=["last_train_unknown"])
DONGBAEK = opt("walk_to_station", "28T23:00:00", "Dongbaek", walk=18, extra=15)
JUNGDONG = opt("walk_to_station", "28T23:00:00", "Jung-dong", walk=17, extra=20)
RESULT = {"baseline": BASELINE, "options": [EARLIER, LATER, DONGBAEK, JUNGDONG]}


def test_score_route_counts_travel_early_wait_walk_and_penalties():
    early = score_route(EARLIER, BASELINE)
    assert early.travel_min == 39 and early.arrive_at == "2026-11-28T22:59:00+09:00"
    assert early.breakdown == {"travel": 39.0, "early": 40.0, "wait": 0.0, "walk": 0.0, "penalty": 0.0}
    assert early.score == -79.0
    late = score_route(LATER, BASELINE)
    assert late.breakdown["wait"] == 60 * w.ROUTE_W_WAIT
    assert late.breakdown["penalty"] == w.ROUTE_PENALTY["last_train_unknown"]
    walk = score_route(DONGBAEK, BASELINE)
    assert walk.travel_min == 54 and walk.breakdown["walk"] == 18 * w.ROUTE_W_WALK and walk.score == -63.0


def test_crowded_option_gets_penalty():
    crowded = score_route(opt("walk_to_station", "28T23:00:00", walk=5, extra=3, avoids=False), BASELINE)
    assert crowded.breakdown["penalty"] == w.ROUTE_PENALTY["crowded"]


def test_scene7_labels_best_earliest_and_least_walking():
    ranked = rank_routes(RESULT)
    assert [r.option["station"] for r in ranked] == ["Dongbaek", "Jung-dong", "Haeundae"]
    labels = {(r.option["type"], r.option["station"]): r.labels for r in ranked}
    assert labels[("walk_to_station", "Dongbaek")] == ["best"]
    # 일찍 떠나는 안이 가장 빨리 도착하고 걷지도 않는다. 이름 두 개를 갖고, 남은 한 자리는 점수 순(중동)으로 채운다
    assert labels[("shift_earlier", "Haeundae")] == ["earliest_arrival", "least_walking"]
    assert labels[("walk_to_station", "Jung-dong")] == []


def test_limit_never_drops_a_labelled_option():
    ranked = rank_routes(RESULT, limit=1)
    assert {tuple(r.labels) for r in ranked} == {("best",), ("earliest_arrival", "least_walking")}


def test_missed_last_train_is_excluded():
    missed = opt("shift_later", "29T00:00:00", warnings=["last_train_missed"])
    ranked = rank_routes({"baseline": BASELINE, "options": [missed, DONGBAEK]})
    assert [r.option["station"] for r in ranked] == ["Dongbaek"]
    assert ranked[0].labels == ["best", "earliest_arrival", "least_walking"]
    assert rank_routes({"baseline": BASELINE, "options": [missed]}) == []


def test_no_options_or_error_returns_empty():
    assert rank_routes({"baseline": BASELINE, "options": []}) == []
    assert rank_routes({"error": {"code": "event_not_found", "message": "x"}}) == []


def test_deterministic_and_ties_keep_original_order():
    a = opt("walk_to_station", "28T23:00:00", "A", walk=10, extra=10)
    b = opt("walk_to_station", "28T23:00:00", "B", walk=10, extra=10)
    first = rank_routes({"baseline": BASELINE, "options": [a, b]})
    assert [r.option["station"] for r in first] == ["A", "B"]
    assert first == rank_routes({"baseline": BASELINE, "options": [a, b]})


def test_real_scene7_result_ranks_walking_to_dongbaek_first():
    result = return_options("2026-11-28", place_id="haeundae-beach")
    ranked = rank_routes(result)
    assert ranked[0].option["station"] == "Dongbaek" and ranked[0].labels[0] == "best"
    assert all(r.excluded is None for r in ranked)
    assert {r.option["type"] for r in ranked} <= {"shift_earlier", "shift_later", "walk_to_station"}
