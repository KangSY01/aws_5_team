"""부산 2호선 역명 XLSX 에서 한글·일본어·중국어(간체·번체) 열만 뽑아 scripts/busan_line2_station_names.csv 로 저장한다.

출처: 국가철도공단_도시광역철도 부산 2호선 역명_20260630 (공공데이터포털, 이용허락범위 제한 없음)
원본: app/data/raw/krna_busan_line2_station_names_20260630.xlsx (git 에 올리지 않는다)

일회성 스크립트다. openpyxl 은 프로젝트 의존성이 아니므로 backend/ 에서 이렇게 실행한다.

    uv run --with openpyxl python -m scripts.extract_station_names

API 를 부르지 않는다. 만든 CSV(UTF-8, BOM 없음)는 커밋하고, scripts/build_stations.py 가 읽는다.
"""
import csv
import sys

import openpyxl

from scripts.fetch_places import PLACES_PATH, SCRIPTS_DIR

XLSX_PATH = PLACES_PATH.parent / "raw" / "krna_busan_line2_station_names_20260630.xlsx"
CSV_PATH = SCRIPTS_DIR / "busan_line2_station_names.csv"
COLUMNS = {"역명": "역명", "역명(일본어)": "ja", "역명(중국어간체)": "zh-Hans", "역명(중국어번체)": "zh-Hant"}  # XLSX 열 → CSV 열


def main() -> int:
    rows = openpyxl.load_workbook(XLSX_PATH, read_only=True).worksheets[0].iter_rows(values_only=True)
    header = list(next(rows))
    picks = [header.index(column) for column in COLUMNS]  # 열이 없으면 ValueError 로 멈춘다
    out = [[str(row[i] or "").strip() for i in picks] for row in rows if row[picks[0]]]
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(COLUMNS.values())
        writer.writerows(out)
    print(f"{XLSX_PATH.name} → {CSV_PATH.name} {len(out)}행")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
