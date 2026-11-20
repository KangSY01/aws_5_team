# 데이터 출처

이 서비스가 쓰는 데이터는 모두 공공데이터이고, 크롤링한 데이터는 없습니다. 네이버 블로그 같은 웹 게시물이나 리뷰는 약관·저작권 문제로 수집하지 않습니다.
날씨만 실시간으로 조회하고(DynamoDB 캐시 60분), 나머지는 미리 받아 `backend/app/data/`에 둔 파일을 읽습니다. 그래서 외부 API가 멈춰도 데모가 동작합니다.

## 출처별 사용처

| 데이터 | 제공 기관 · API | 저장 파일 | 쓰는 도구 | 기준 |
|---|---|---|---|---|
| 관광지 정보, 다국어 이름(영·일·중 간체·번체), 좌표 | 한국관광공사 국문·영문·일문·중문 관광정보서비스 (KorService2, EngService2, JpnService2, ChsService2, ChtService2) | `places.json` 35곳, `places_sources.json` | `search_places`, `get_place_info` | 2026-11-20 수집 |
| 운영시간·휴무일 | 한국관광공사 TourAPI `detailIntro2` | `hours.json` 35곳 | `get_hours` | 2026-11-20 수집. 원문은 `raw_text`에 보관, 단순 패턴만 시각으로 변환 |
| 축제·행사 | 한국관광공사 TourAPI `searchFestival2` (부산, 2026년 11월), 행사 시간은 `detailIntro2` | `events.json` 14건 | `get_events` | 2026-11-20 수집 |
| 음식점, 대표 메뉴 | 한국관광공사 TourAPI 음식점(`areaBasedList2`, `detailIntro2`) | `restaurants.json` 43곳 | `get_restaurants` | 해운대·자갈치·감천·서면역 반경 500m. 식단·가격 정보는 없음 |
| 관광지 집중률 | 한국관광공사 관광지 집중률 방문자 추이 예측 (TatsCnctrRateService) | `congestion.json` 23곳 | `get_crowd` | 2026-11-18 ~ 12-17 일 단위 예측 |
| 날씨 | 기상청 단기예보 조회서비스 (VilageFcstInfoService_2.0) | 실시간 조회 + DynamoDB 캐시 | `get_weather` | 약 3일 이내만 제공 |
| 지하철역 이름·좌표·노선 | 부산교통공사 도시철도역사정보 (파일데이터) | `stations.json` 108곳 | `get_transit_info`, `get_return_options` | 1~4호선. 동해선·경전철 없음 |
| 지도 | © OpenStreetMap contributors | — | 프론트엔드 MapLibre | — |

## 코드가 계산한 값 (데이터가 아닌 추정)

아래 값은 공공데이터를 바탕으로 코드가 규칙으로 계산한 추정값입니다. 실제 경로 조회나 실측 결과가 아니며, 답변에서도 "약 N분"으로 말합니다.

| 값 | 파일 · 코드 | 규칙 |
|---|---|---|
| 장소 사이 이동 시간 | `travel_times.json` (595쌍) | 직선거리 × 1.3. 1.2km 이하는 도보(시속 4.5km), 그 이상은 지하철(시속 25km + 대기·환승 10분) |
| 요일 혼잡 규칙 | `guardian/thresholds.py` | 집중률이 없는 12곳은 토요일 medium, 일요일 low |
| 행사일 혼잡 | `get_events` | 7일 이하 행사는 기간 전체, 그보다 긴 행사는 개막일만 행사일로 봄 |
| 축제 후 귀가 혼잡 | `get_return_options` | 행사 대표 장소의 가까운 역을 행사 종료 30분 전 ~ 60분 뒤 혼잡으로 봄 (가정) |
| 큐레이션(태그, 혼잡·비 대안) | `curation.json` | 분류 기반 태그, 이동 30분 안의 비슷한 장소·실내 장소 |
| 외국인 친화도 | `curation.json` | 관광공사 다국어 정보가 제공되는 언어 수(0~3) |

## 해석 원칙

- 집중률은 장소마다 자기 최고 시기를 100으로 둔 상대값입니다. 서로 다른 장소끼리 비교하지 않습니다("해운대치고 붐빔"은 되고 "광안리보다 붐빔"은 안 됨).
- 집중률은 일 단위 예측이라 시간대별 혼잡을 말하지 않습니다.
- 운영시간·요금·식단처럼 데이터에 없는 값은 지어내지 않고 "모른다"고 답합니다.
- 외국어 이름은 관광공사 다국어 서비스에 있는 이름만 씁니다. 없으면 다른 언어 이름으로 대신 보여 줍니다.
- 카카오 경로 API 결과는 저장하지 않습니다(약관).

## 다시 받는 방법

`backend/`에서 실행합니다. 공공데이터포털 키(`DATA_GO_KR_KEY_DECODING`)가 `.env`에 있어야 합니다.

```
uv run --env-file .env python -m scripts.fetch_places
uv run --env-file .env python -m scripts.backfill_names --reuse-raw
uv run --env-file .env python -m scripts.fetch_hours
uv run --env-file .env python -m scripts.fetch_events
uv run --env-file .env python -m scripts.fetch_restaurants
uv run python -m scripts.build_congestion
uv run python -m scripts.build_travel_times
uv run python -m scripts.build_curation
uv run python -m scripts.build_stations
```

원본 응답은 `backend/app/data/raw/`에 저장되고 git에는 올리지 않습니다. 저장된 응답이 있으면 다시 호출하지 않습니다.
