"""places.json 좌표로 모든 장소 쌍의 이동 시간 추정표(travel_times.json)를 만든다. backend/ 에서 실행한다.

    uv run python -m scripts.build_travel_times

API 를 부르지 않는다. places.json 이 바뀌면 다시 실행한다 (tests/test_lookup.py 가 표와 places.json 이 맞는지 확인한다).

추정 규칙 (실제 경로 조회 값이 아니다. .kiro/steering/data-rules.md 「이동 시간」과 같다)
  경로 거리 = 직선거리(haversine) × 1.3
  경로 거리 1.2km 이하  walk   : 시속 4.5km
  그보다 멀면           subway : 평균 시속 25km + 대기·환승 10분
  분은 올림한다. 양방향은 같은 값이라 쌍마다 한 번만 적는다.
카카오 경로 API 결과는 쓰지 않고 저장하지도 않는다.
"""
import json
import math
import sys
from pathlib import Path

from scripts.fetch_places import PLACES_PATH, haversine_m

OUT_PATH = PLACES_PATH.parent / "travel_times.json"
RULE = {"route_factor": 1.3, "walk_max_km": 1.2, "walk_kmh": 4.5, "subway_kmh": 25, "subway_overhead_min": 10}


def estimate(straight_m: float) -> dict:
    """직선거리(m) → {"route_km", "minutes", "mode"}."""
    route_km = straight_m / 1000 * RULE["route_factor"]
    if route_km <= RULE["walk_max_km"]:
        mode, minutes = "walk", route_km / RULE["walk_kmh"] * 60
    else:
        mode, minutes = "subway", route_km / RULE["subway_kmh"] * 60 + RULE["subway_overhead_min"]
    # round: 부동소수점 오차(16.0000001)로 1분이 더 올라가지 않게 한다
    return {"route_km": round(route_km, 2), "minutes": math.ceil(round(minutes, 6)), "mode": mode}


def build_pairs(places: list[dict]) -> list[dict]:
    """모든 장소 쌍(순서 없음)의 추정 이동 시간. places.json 순서를 따른다."""
    pairs = []
    for i, a in enumerate(places):
        for b in places[i + 1:]:
            pairs.append({"from_place_id": a["place_id"], "to_place_id": b["place_id"],
                          **estimate(haversine_m(a["lat"], a["lng"], b["lat"], b["lng"]))})
    return pairs


def dump_table(pairs: list[dict]) -> str:
    """travel_times.json 본문. 쌍 하나를 한 줄로 쓴다."""
    head = {
        "note": "추정값이다. 실제 경로 조회 결과가 아니다. scripts/build_travel_times.py 가 places.json 좌표로 만든다.",
        "rule": RULE,
    }
    rows = ",\n".join("    " + json.dumps(p, ensure_ascii=False) for p in pairs)
    return json.dumps(head, ensure_ascii=False, indent=2)[:-2] + ',\n  "pairs": [\n' + rows + "\n  ]\n}\n"


def main(out_path: Path = OUT_PATH) -> int:
    places = json.loads(PLACES_PATH.read_text(encoding="utf-8"))
    pairs = build_pairs(places)
    out_path.write_text(dump_table(pairs), encoding="utf-8", newline="\n")
    modes = {m: sum(p["mode"] == m for p in pairs) for m in ("walk", "subway")}
    print(f"장소 {len(places)}곳, 쌍 {len(pairs)}개 저장 ({out_path.name}): {modes}, "
          f"최대 {max(p['minutes'] for p in pairs)}분")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
