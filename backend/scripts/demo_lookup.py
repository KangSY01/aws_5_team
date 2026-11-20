"""조회 도구 네 개를 한 번씩 불러 결과를 출력한다 (점검 시연용). backend/ 에서 실행한다.

    $env:USE_MOCK = "1"; uv run python -m scripts.demo_lookup          # 샘플 데이터, 네트워크 없음
    uv run --env-file .env python -m scripts.demo_lookup               # .env 의 USE_MOCK 값을 따른다
"""

import json
import sys

from app import config
from app.tools import lookup

DEMO_DATE = "2026-11-21"  # 샘플 일정(sample_plan.json)의 날짜


def show(title: str, result) -> None:
    print(f"\n# {title}")
    rows = result.get("hourly") if isinstance(result, dict) else result
    if isinstance(rows, list) and rows:  # 목록은 한 줄에 한 항목
        if isinstance(result, dict):
            print(json.dumps({k: v for k, v in result.items() if k != "hourly"}, ensure_ascii=False), "hourly:")
        for row in rows:
            print("  " + json.dumps(row, ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False))


def main() -> int:
    print(f"USE_MOCK={int(config.USE_MOCK)}")
    show('search_places(query="market", indoor=True)', lookup.search_places(query="market", indoor=True))
    show('search_places(query="", category="museum")', lookup.search_places(query="", category="museum"))
    show(f'get_crowd("gamcheon-village", "{DEMO_DATE}")', lookup.get_crowd(place_id="gamcheon-village", date=DEMO_DATE))
    show(f'get_crowd("haeundae-beach", "{DEMO_DATE}")', lookup.get_crowd(place_id="haeundae-beach", date=DEMO_DATE))
    show(f'get_weather("{DEMO_DATE}")', lookup.get_weather(date=DEMO_DATE))
    show('get_weather("2026-12-25")  예보 없는 날짜', lookup.get_weather(date="2026-12-25"))
    show('get_hours("busan-tower")', lookup.get_hours(place_id="busan-tower"))
    show('get_hours("no-such-place")  실패 형식', lookup.get_hours(place_id="no-such-place"))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
