"""부산 도시철도 역 표(stations.json)를 scripts/busan_stations.csv 로 만든다. backend/ 에서 실행한다.

    uv run python -m scripts.build_stations

API 를 부르지 않는다. busan_stations.csv(부산교통공사 도시철도 역 정보, 1~4호선)나 places.json 이 바뀌면 다시 실행한다.
출력 app/data/stations.json — get_return_options(app/tools/return_options.py)가 읽는다
  station  CSV 의 name_en 그대로. places.json 의 nearest_station 과 정확히 같은 문자열일 때만 연결된다
  name_ko  CSV 의 역명 ("서면역(1호선)" 같은 노선 표기는 뗀다)
  lines    노선 번호 목록 (참고용. 도구는 노선·환승을 말하지 않는다)
  lat·lng  역 좌표. 환승역(name_en 이 같은 행)은 한 항목으로 합치고 좌표는 행들의 평균
  names    ja·zh-Hans·zh-Hant 역명 (키는 places.json 의 names 와 같다). busan_line2_station_names.csv
           (국가철도공단_도시광역철도 부산 2호선 역명_20260630, scripts/extract_station_names.py 가 만든다)에 있는 값만 넣는다.
           한글 역명을 '역'과 괄호 표기를 떼고 name_ko 와 비교한다. 2호선 밖 역과 빈 칸은 넣지 않는다 (지어내지 않는다)
동해선·경전철 역은 CSV 에 없다. places.json 의 nearest_station 중 표에 없는 값과 이름이 안 맞은 2호선 역은 경고로 출력한다.
"""
import csv
import json
import re
import sys
from pathlib import Path

from scripts.fetch_places import PLACES_PATH, SCRIPTS_DIR

CSV_PATH = SCRIPTS_DIR / "busan_stations.csv"
NAMES_CSV_PATH = SCRIPTS_DIR / "busan_line2_station_names.csv"
NAME_LANGS = ("ja", "zh-Hans", "zh-Hant")
OUT_PATH = PLACES_PATH.parent / "stations.json"
NOTE = ("부산교통공사 도시철도 역 정보(1~4호선)로 만든 역 표. scripts/build_stations.py 가 busan_stations.csv 로 만든다. "
        "환승역은 한 항목(좌표는 평균)이다. 동해선·경전철 역은 없다.")


def build_stations(rows: list[dict]) -> list[dict]:
    """CSV 행 → 역 목록 (CSV 에 처음 나온 순서). name_en 이 같은 행은 한 역으로 합친다."""
    merged: dict[str, list[dict]] = {}
    for row in rows:
        merged.setdefault(row["name_en"].strip(), []).append(row)
    return [
        {
            "station": name,
            "name_ko": re.sub(r"\(\d호선\)$", "", group[0]["역명"].strip()),
            "lines": sorted({re.search(r"(\d)호선", r["노선명"]).group(1) for r in group}),
            "lat": round(sum(float(r["lat"]) for r in group) / len(group), 6),
            "lng": round(sum(float(r["lng"]) for r in group) / len(group), 6),
        }
        for name, group in merged.items()
    ]


def _name_key(name: str) -> str:
    """비교용 역명: 괄호 표기("(1호선)", "(사상구청)")와 끝의 '역'을 뗀다."""
    return re.sub(r"\(.*?\)", "", name).strip().removesuffix("역")


def add_names(stations: list[dict], name_rows: list[dict]) -> list[str]:
    """2호선 역에 names(ja, zh-Hans, zh-Hant)를 붙이고, 이름이 안 맞은 2호선 역의 station 목록을 돌려준다."""
    by_key = {_name_key(row["역명"]): row for row in name_rows}
    unmatched = []
    for station in stations:
        if "2" not in station["lines"]:
            continue
        row = by_key.get(_name_key(station["name_ko"]))
        if row is None:
            unmatched.append(station["station"])
            continue
        names = {lang: row[lang].strip() for lang in NAME_LANGS if row[lang].strip()}
        if names:
            station["names"] = names
    return unmatched


def read_name_rows() -> list[dict]:
    with NAMES_CSV_PATH.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def dump_stations(stations: list[dict]) -> str:
    """stations.json 본문. 역 하나를 한 줄로 쓴다."""
    rows = ",\n".join("    " + json.dumps(s, ensure_ascii=False) for s in stations)
    return json.dumps({"note": NOTE}, ensure_ascii=False, indent=2)[:-2] + ',\n  "stations": [\n' + rows + "\n  ]\n}\n"


def main(out_path: Path = OUT_PATH) -> int:
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    stations = build_stations(rows)
    unmatched = add_names(stations, read_name_rows())
    out_path.write_text(dump_stations(stations), encoding="utf-8", newline="\n")
    print(f"CSV {len(rows)}행 → 역 {len(stations)}곳 저장 ({out_path.name}), "
          f"환승역 {[s['station'] for s in stations if len(s['lines']) > 1]}")
    print("언어별 채운 역 수: " + ", ".join(f"{lang} {sum(lang in s.get('names', {}) for s in stations)}" for lang in NAME_LANGS))
    for name in unmatched:
        print(f"[경고] 2호선 역 {name!r} 이 {NAMES_CSV_PATH.name} 의 역명과 맞지 않아 names 를 넣지 않았습니다.")
    known = {s["station"] for s in stations}
    for place in json.loads(PLACES_PATH.read_text(encoding="utf-8")):
        if place["nearest_station"] and place["nearest_station"] not in known:
            print(f"[경고] {place['place_id']} 의 nearest_station {place['nearest_station']!r} 이 역 표에 없습니다.")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
