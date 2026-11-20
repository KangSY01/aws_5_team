"""귀가 경로 점수 (rank_routes, 데모 장면 7). LLM 미사용, 순수 파이썬. 같은 입력이면 항상 같은 결과.

get_return_options 결과(dict)를 그대로 받아 options 를 채점하고, 1등 하나 대신 이름 붙은 2~3안을 고른다.
- best: 종합 점수 1위
- earliest_arrival: 도착역에 가장 빨리 닿는 안
- least_walking: 가장 덜 걷는 안
이동 시간·혼잡은 get_return_options 의 규칙 추정값을 그대로 쓴다. 새 숫자를 만들지 않는다.
"""

import datetime as dt

from pydantic import BaseModel

from app.ranking import weights as w

LABELS = ("best", "earliest_arrival", "least_walking")


class RouteScore(BaseModel):
    """귀가 후보 하나의 점수. option 은 get_return_options 의 options 항목 그대로다."""

    option: dict
    score: float  # -비용(분 환산), 소수 첫째 자리. 높을수록 좋다
    travel_min: int  # 출발 후 도착역까지 (baseline.minutes + extra_min)
    arrive_at: str  # depart_at + travel_min (ISO, +09:00)
    breakdown: dict[str, float]  # 비용 항목 → 분 환산 값 (travel, early, wait, walk, penalty)
    labels: list[str] = []  # LABELS 중 이 안이 1위인 것
    excluded: str | None = None  # 후보에서 뺀 사유 (예: "last_train_missed")


def score_route(option: dict, baseline: dict) -> RouteScore:
    """options 항목 하나를 채점한다. baseline 은 get_return_options 결과의 baseline (계획 출발 시각·기본 이동 분)."""
    planned = dt.datetime.fromisoformat(baseline["depart_at"])
    depart = dt.datetime.fromisoformat(option["depart_at"])
    travel_min = baseline["minutes"] + option["extra_min"]
    shift_min = (depart - planned).total_seconds() / 60
    penalty = sum(w.ROUTE_PENALTY.get(code, 0.0) for code in option["warnings"])
    if not option["avoids_congestion"]:
        penalty += w.ROUTE_PENALTY["crowded"]
    breakdown = {
        "travel": travel_min * w.ROUTE_W_TRAVEL,
        "early": max(0.0, -shift_min) * w.ROUTE_W_EARLY,
        "wait": max(0.0, shift_min) * w.ROUTE_W_WAIT,
        "walk": option["walk_min"] * w.ROUTE_W_WALK,
        "penalty": penalty,
    }
    excluded = next((code for code in option["warnings"] if code in w.ROUTE_EXCLUDE_WARNINGS), None)
    return RouteScore(
        option=option,
        score=round(-sum(breakdown.values()), 1),
        travel_min=travel_min,
        arrive_at=(depart + dt.timedelta(minutes=travel_min)).isoformat(),
        breakdown={k: round(v, 1) for k, v in breakdown.items()},
        excluded=excluded,
    )


def rank_routes(result: dict, *, limit: int = 3) -> list[RouteScore]:
    """get_return_options 결과의 options 를 채점해 이름 붙은 안을 점수 높은 순으로 돌려준다.

    - 막차를 놓치는 안(last_train_missed)은 뺀다.
    - LABELS 마다 1위 안을 먼저 넣고(한 안이 여러 이름을 가질 수 있다), 남은 자리는 점수 순으로 채운다.
    - 동점은 options 원래 순서(get_return_options 가 extra_min 순으로 정렬한 순서)를 따른다.
    - options 가 비었거나(혼잡하지 않음) 오류 dict 면 빈 목록.
    """
    if "error" in result or not result.get("options"):
        return []
    scored = [score_route(o, result["baseline"]) for o in result["options"]]
    order = {id(s): i for i, s in enumerate(scored)}
    kept = [s for s in scored if s.excluded is None]
    if not kept:
        return []

    by_score = sorted(kept, key=lambda s: (-s.score, order[id(s)]))
    winners = {
        "best": by_score[0],
        "earliest_arrival": min(
            kept, key=lambda s: (dt.datetime.fromisoformat(s.arrive_at), -s.score, order[id(s)])
        ),
        "least_walking": min(kept, key=lambda s: (s.option["walk_min"], -s.score, order[id(s)])),
    }
    for label in LABELS:
        winners[label].labels.append(label)

    picked = [s for s in by_score if s.labels]
    picked += [s for s in by_score if not s.labels][: max(0, limit - len(picked))]
    return sorted(picked, key=lambda s: (-s.score, order[id(s)]))
