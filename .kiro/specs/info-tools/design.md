# Design Document

## Overview

조회 도구 2개(`get_restaurants`, `get_transit_info`)와 음식점 수집 스크립트 1개(`fetch_restaurants.py`)를 추가합니다. 기존 조회 도구(`lookup.py`)와 귀가 도구(`return_options.py`)의 규칙을 그대로 따릅니다.

- 도구는 LLM과 외부 API를 쓰지 않는 순수 파이썬입니다. 파일은 `backend/app/data/`에서만 읽습니다.
- 실패는 `{"error": {"code", "message"}}`로 돌려줍니다(`lookup.LookupFailure`, `lookup._safe` 재사용).
- 새 필드 이름은 `snake_case`, 시각이 아닌 값은 모두 정수·문자열·목록입니다. Guardian과 프론트엔드가 그대로 읽을 수 있습니다.
- 공용 파일은 건드리지 않습니다. 에이전트 등록·출처 조립은 「에이전트 연결 수정안」에 수정안만 적습니다.

### 수정 범위

| 종류 | 경로 | 비고 |
|---|---|---|
| 새 파일 | `backend/app/tools/restaurants.py` | `get_restaurants` |
| 새 파일 | `backend/app/tools/transit.py` | `get_transit_info` |
| 새 파일 | `backend/scripts/fetch_restaurants.py`, `backend/scripts/restaurant_seeds.json` | 수집 |
| 새 데이터 | `backend/app/data/restaurants.json`, `backend/app/data/raw/restaurants/` | raw는 git에 올리지 않는다(기존 `raw/` 규칙 확인) |
| 새 테스트 | `backend/tests/test_restaurants.py`, `backend/tests/test_transit.py` | |
| 프론트엔드 mock | 도구 결과를 화면에 쓰게 되면 그 시점에 복사본을 같은 PR에서 맞춘다 | 지금은 해당 없음 |
| 문서 | `.kiro/steering/data-rules.md`에 「음식점」·「대중교통」 절 추가 | steering은 공용 `team.md`가 아니므로 B가 수정 가능한지 팀에 확인(열린 질문 9) |

## Architecture

```mermaid
flowchart LR
  subgraph 수집 [사전 수집 (사람이 실행)]
    SEED[restaurant_seeds.json<br/>Anchor place_id] --> COL[fetch_restaurants.py]
    TOUR[TourAPI locationBasedList2<br/>국문 39, 외국어 4개 서비스] --> COL
    COL --> RAW[raw/restaurants/*.json]
    COL --> RT[restaurants.json]
  end
  subgraph 도구 [런타임 (LLM 없음)]
    RT --> GR[get_restaurants]
    PL[places.json] --> GR
    PL --> GT[get_transit_info]
    ST[stations.json] --> GT
    TT[travel_times.json rule] --> GT
  end
  GR --> AG[chat 에이전트]
  GT --> AG
  GT --> GU[Guardian / 프론트엔드]
```

### 역할 분리

- LLM: 어떤 음식점·이동 방법을 고를지, 이유와 다국어 문장.
- 코드: 거리, 도보·지하철 분, 정렬, 장소·역 ID 검증, 역 표 연결.

## Components and Interfaces

### 1. 수집 스크립트 `scripts/fetch_restaurants.py`

실행(backend/에서):

```
uv run --env-file .env python -m scripts.fetch_restaurants
uv run python -m scripts.fetch_restaurants --offline
uv run --env-file .env python -m scripts.fetch_restaurants --reuse-raw
```

`fetch_places.py`의 순수 함수를 import해 다시 씁니다: `haversine_m`, `parse_items`, `normalize_korean`, `strip_korean`, `match_kind`, `pick_foreign`, `FetchError`, `request_json`, `load_json`. 일치 규칙을 복사하지 않아 `fetch_places`와 같은 규칙이 유지됩니다. 단 `fetch_places._call_and_save`는 모듈 전역(`OFFLINE`, `REUSE_RAW`)을 읽으므로, 이 스크립트는 같은 동작의 작은 호출 함수를 따로 둡니다(raw 경로만 다름).

처리 순서:

1. 시드 읽기: `restaurant_seeds.json` = `["haeundae-beach", "jagalchi-market", "gamcheon-village", ...]`. 각 값이 `places.json`에 없으면 시작 전에 오류로 끝냅니다.
2. Anchor마다 국문 `locationBasedList2`(`mapX`, `mapY`, `radius=1000`, `contentTypeId=39`, `arrange=E`)를 페이지(`numOfRows=100`, 최대 5쪽)로 받습니다. `addr1`이 `부산`으로 시작하는 항목만 씁니다.
3. 외국어 4개 서비스에 같은 좌표·반경으로 `locationBasedList2`를 받습니다. 외국어 음식점 `contentTypeId`는 국문(39)과 번호 체계가 달라(예상 82, 열린 질문 1) 처음에는 타입으로 거르지 않고 반경 결과 전체를 받아 `pick_foreign`으로 국문 항목마다 일치시킵니다. 타입 필터를 쓰면 호출 수만 줄이고 결과 규칙은 바뀌지 않아야 합니다.
4. 국문 음식점마다 `pick_foreign(kor, 외국어 후보)`를 언어별로 호출해 `names`를 채웁니다. 일치가 없는 언어는 비우고 검토 목록(`restaurants_review.csv`)에 사유를 남깁니다. 기존 장소와 달리 이름을 덮어쓸 기준 파일이 없으므로 `kept_existing` 규칙은 없습니다.
5. `cuisine`: 국문 응답의 분류 코드(`lclsSystm3` 등, `kor_class`에 원본 저장)를 `CUISINE_BY_CLASS` 표로 바꿉니다. 표에 없는 코드는 `null`입니다. 표는 실제 응답을 확인하고 채웁니다(열린 질문 2).
6. `menu_raw`: 국문 응답에는 대표 메뉴가 없으므로 `detailIntro2`(`contentTypeId=39`)의 `firstmenu`·`treatmenu` 원문을 쓰는 방식을 후보로 둡니다. 호출 수가 음식점 수만큼 늘어 필수는 아닙니다(열린 질문 3). 호출하지 않으면 모든 음식점의 `menu_raw`는 `null`입니다.
7. 음식점을 `restaurant_id`로 합치고(Anchor 반경이 겹치면 한 번만 저장), 정렬해 `restaurants.json`에 씁니다.

API 호출 추정: Anchor 3곳 × (국문 최대 5쪽 + 외국어 4개 × 최대 5쪽) ≈ 최대 75회. `--reuse-raw`로 다시 돌릴 때 새 호출이 없습니다. 키는 raw에 저장하지 않습니다.

### 2. `get_restaurants` (`tools/restaurants.py`)

```python
@tool
@_safe
def get_restaurants(place_id: str, radius_m: int = 500, limit: int = 10) -> dict: ...
```

- 순수 함수 `restaurants_near(place_id, radius_m, limit)`와 `@tool` 래퍼를 나눕니다(`return_options.py`와 같은 구조).
- `restaurants.json`은 `functools.lru_cache`로 한 번만 읽습니다(`lookup._travel_table`과 같은 방식, 경로를 인자로 받아 테스트에서 바꿀 수 있게 함).
- 거리: `haversine_m`(장소 좌표 ↔ 음식점 좌표) 정수 반올림. 도보 분: `ceil(round(경로계수 × 직선거리_km / 4.5 × 60, 6))`(`return_options.walk_minutes`와 같은 식, 단 입력이 역이 아닌 좌표이므로 작은 헬퍼를 `transit.py`에 두고 두 도구가 공유).
- 정렬 키 `(distance_m, restaurant_id)`. 반경은 포함(`<=`).
- 반경 안 판단은 반올림 전 거리로 합니다(경계 값이 반올림 때문에 들어오거나 빠지지 않게).

반환 형식:

```json
{
  "place_id": "haeundae-beach",
  "radius_m": 500,
  "total_in_radius": 23,
  "restaurants": [
    {
      "restaurant_id": "kto-2763589",
      "name_ko": "...",
      "names": {"en": "...", "ja": "..."},
      "lat": 35.16, "lng": 129.16,
      "address_ko": "부산광역시 해운대구 ...",
      "cuisine": "korean",
      "menu_raw": null,
      "distance_m": 180,
      "walk_min": 3
    }
  ],
  "basis": {
    "kind": "collected_public_data",
    "source": "한국관광공사 TourAPI 음식점 정보 (공공데이터포털)",
    "collected_at": "2026-11-21",
    "distance": "straight_line_estimate",
    "diet_info": "not_available",
    "note": "Opening hours, closed days, prices, menus and dietary options (halal, vegetarian, allergens) are not included. Ask the restaurant."
  }
}
```

오류 코드: `place_not_found`, `restaurants_not_collected`, `invalid_argument`, `data_unavailable`, `internal_error`.

### 3. `get_transit_info` (`tools/transit.py`)

```python
@tool
@_safe
def get_transit_info(from_place_id: str, to_place_id: str | None = None, to_station: str | None = None) -> dict: ...
```

- 역 표 읽기는 `lookup._load_json("stations.json")`, 규칙은 `travel_times.json`의 `rule`을 `return_options`와 같은 방식(`RULE_KEYS`)으로 읽습니다.
- 지하철 분은 `return_options.subway_minutes(a, b, rule)`를 그대로 import해 씁니다. 이 함수는 B의 같은 모듈이며 `build_travel_times.py`의 지하철 규칙과 같은 값을 돌려줍니다. 도보 분 함수(`walk_minutes`)는 입력이 `lat`·`lng`만 있으면 되므로 장소 dict에도 쓸 수 있습니다. 직선거리 헬퍼 `_straight_km`는 비공개이므로 import하지 않고, 같은 식을 `scripts.fetch_places.haversine_m`(미터)로 계산하거나 `return_options`에 공개 별칭을 추가하는 안 중 하나를 고릅니다(열린 질문 5). 기본안은 `return_options.walk_minutes`와 `subway_minutes`만 import하고 거리 계산은 둘에 맡기는 것입니다.
- 장소 → 역: `places[place_id]["nearest_station"]`을 `stations`에서 이름 그대로 찾습니다. 못 찾거나 `null`이면 `no_station`(메시지에 동해선·경전철은 데이터에 없다고 적음). 현재 `OSIRIA`(해동용궁사)와 `nearest_station: null`인 장소가 해당합니다.
- `to_station`: `casefold`와 `strip`으로 `stations`의 키와 맞춥니다.
- 입력 검증 순서(오류 코드가 결정적으로 나오게): `missing_argument` → `place_not_found`(from) → `same_place` → 도착 결정(`to_station` 우선, 아니면 `to_place_id` 검증) → `station_not_found` / `no_station`.
- `same_place`는 `to_station`이 없을 때 `from_place_id == to_place_id`이면 돌려줍니다.
- 도보 20분 초과 경고 상수 `FAR_FROM_STATION_MIN = 20`은 `return_options.WALK_ALT_MAX_MIN`과 같은 값입니다. 값을 두 곳에 두지 않기 위해 import합니다.

반환 형식:

```json
{
  "from": {
    "place_id": "haeundae-beach",
    "station": "Haeundae", "station_ko": "해운대역",
    "lines": ["2"], "is_transfer_station": false,
    "walk_to_station_min": 9,
    "warnings": []
  },
  "to": {
    "place_id": null,
    "station": "Seomyeon", "station_ko": "서면역",
    "lines": ["1", "2"], "is_transfer_station": true,
    "walk_from_station_min": 0,
    "warnings": []
  },
  "subway": {"minutes": 39, "same_station": false},
  "total_min": 48,
  "basis": {
    "kind": "rule", "measured": false,
    "travel_time_rule": {"route_factor": 1.3, "subway_kmh": 25, "subway_overhead_min": 10, "walk_kmh": 4.5},
    "note": "Estimated from coordinates, not routes or timetables. 'lines' are the lines that serve each station (reference only). Transfers between the two stations are not computed.",
    "not_included": ["timetable", "real_time", "first_last_train", "fare", "transfer_walk"],
    "coverage": "Busan Metro lines 1-4 only. Donghae Line and light rail stations are not in the station table."
  }
}
```

- `to_place_id`로 받은 도착은 `to.place_id`에 그 값이 들어가고 `to.walk_from_station_min`은 역 → 장소 도보입니다.
- `total_min`은 세 값의 합이며 `ceil`을 한 번 더 하지 않습니다(각 값이 이미 올림된 정수).
- `station_ko`는 `stations.json`의 `name_ko`입니다.
- `is_transfer_station`은 `len(lines) >= 2`이고 `lines`는 Station_Table 값 그대로입니다. 두 역 사이의 환승 횟수·호선 선택은 계산하지 않습니다.

오류 코드: `missing_argument`, `place_not_found`, `same_place`, `station_not_found`, `no_station`, `data_unavailable`, `internal_error`.

## Data Models

`restaurants.json` (루트가 dict인 이유: `places.json`과 달리 수집 메타데이터와 Anchor 정보가 필요하기 때문):

```json
{
  "note": "한국관광공사 TourAPI 음식점 정보를 scripts/fetch_restaurants.py 로 미리 받아 만든 파일이다. 식단·영업시간은 없다.",
  "collected_at": "2026-11-21",
  "radius_m": 1000,
  "anchors": {
    "haeundae-beach": ["kto-2763589", "kto-..."]
  },
  "restaurants": [
    {
      "restaurant_id": "kto-2763589",
      "name_ko": "...",
      "names": {"en": "...", "ja": "...", "zh-Hans": "...", "zh-Hant": "..."},
      "lat": 35.16, "lng": 129.16,
      "address_ko": "...",
      "cuisine": "korean",
      "kor_class": {"lclsSystm1": "FD", "lclsSystm2": "...", "lclsSystm3": "..."},
      "menu_raw": null
    }
  ]
}
```

Pydantic 모델은 새 파일 `backend/app/tools/restaurants.py` 안에 둡니다. `backend/app/models/`(공용)는 수정하지 않습니다. 모델 위치는 열린 질문 6에 둡니다.

```python
Cuisine = Literal["korean", "western", "japanese", "chinese", "cafe", "other"]

class RestaurantRecord(BaseModel):
    restaurant_id: str          # "kto-" + 국문 contentid
    name_ko: str
    names: dict[Literal["en", "ja", "zh-Hans", "zh-Hant"], str] = {}
    lat: float
    lng: float
    address_ko: str
    cuisine: Cuisine | None
    kor_class: dict[str, str | None]
    menu_raw: str | None = None

class RestaurantTable(BaseModel):
    note: str
    collected_at: str
    radius_m: int
    anchors: dict[str, list[str]]     # place_id → restaurant_id 목록
    restaurants: list[RestaurantRecord]
```

`restaurants.json`에는 `diet`, `halal`, `vegetarian` 같은 필드를 두지 않습니다(`extra="forbid"`로 모델이 막음).

### 장소 선택

- 데모 Anchor: `haeundae-beach`, `jagalchi-market`, `gamcheon-village`.
- 서면역 주변은 `places.json`에 서면 장소가 없어 `place_id`로 지정할 수 없습니다. 새 장소 ID를 만들지 않는다는 규칙 때문에 v1에서는 Anchor에서 제외하고, 역 기준 조회가 필요하면 열린 질문 4에서 정합니다.

### 에이전트 연결 수정안 (적용은 A·공용 담당)

적용하지 않고 수정안만 적습니다.

1. `backend/app/chat/tools.py`(A): `LOOKUP_TOOLS`에 `get_restaurants`, `get_transit_info`를 추가하고 `_PLACE_ID_KEYS`에 이미 있는 `place_id`·`from_place_id`·`to_place_id`가 새 결과 형식에서도 추출되는지 확인합니다. `get_transit_info`의 `from.place_id`는 `from` 안에 중첩되어 있으므로 `walk()`가 재귀로 읽는지 테스트로 확인합니다.
2. `backend/app/chat/answer.py`(A): `build_sources`에 두 도구 출처를 추가합니다. `get_restaurants`는 `basis.source`의 TourAPI 음식점 출처, `get_transit_info`는 「부산교통공사 역 정보와 좌표 기반 추정」 출처를 한 줄씩 냅니다(`return_options`처럼 도구 결과가 아니라 도구 이름으로 조립).
3. `backend/app/prompts.py`·`chat/prompt.py`(D): 한 줄 추가를 제안합니다. "For restaurants and transit, use only the tool results. Say 'about N minutes'. Do not state lines, transfers, timetables, or dietary options that the tool does not return."
4. 도구 호출 상한은 한 요청 5회(`MAX_TOOL_CALLS`)입니다. 도구 2개가 늘어 에이전트가 쓸 수 있는 호출이 충분한지는 A가 확인합니다.
5. `docs/api-contract.md`(공용): 도구 결과는 `sources` 형식 외에 API 계약이 없으므로 수정이 필요 없습니다. 필요해지면 공용 PR로 올립니다.

## Correctness Properties

속성 기반 테스트는 순수 계산(거리 정렬, 도보·지하철 분, 파일 왕복)에만 씁니다. 외부 API와 수집 호출은 고정 응답으로 한 번씩 확인합니다.

### Property 1: 반경 불변식

**Validates: Requirements 3.1, 3.2, 3.4**

임의의 Anchor, `radius_m`(1~1000), `limit`(1~20)에 대해 `get_restaurants` 결과의 모든 `distance_m`은 `radius_m` 이하이고(반올림 오차 1m 허용), `distance_m` 오름차순이며, `len(restaurants) == min(limit, total_in_radius)`이다.

### Property 2: 반경 단조성

**Validates: Requirements 3.1**

`radius_m1 <= radius_m2`이면 `total_in_radius(radius_m1) <= total_in_radius(radius_m2)`이고, 작은 반경 결과(제한 없이)의 ID 집합은 큰 반경 결과의 부분집합이다.

### Property 3: 정렬 결정성

**Validates: Requirements 3.3**

같은 입력을 두 번 호출하면 같은 결과이고, 거리가 같은 항목은 `restaurant_id` 오름차순이다.

### Property 4: 식단 비주장

**Validates: Requirements 4.1, 4.2, 2.3**

어떤 입력에서도 결과(`restaurants`, `basis`)에 `halal`, `vegetarian`, `vegan`, `diet`(`basis.diet_info` 제외) 키가 없고 `basis.diet_info == "not_available"`이다.

### Property 5: 파일 왕복

**Validates: Requirements 2.7, 2.6**

임의의 유효한 `RestaurantTable`에 대해 `model_dump_json` → 파일 → `model_validate_json`한 값이 원래 값과 같다(요구사항 2.7). 수집 스크립트의 직렬화(`dump_restaurants`)도 같은 속성을 만족한다.

### Property 6: ID 유일성

**Validates: Requirements 2.4, 1.9**

수집 결과의 `restaurant_id`는 서로 다르고, `anchors`의 모든 ID는 `restaurants`에 있다.

### Property 7: 수집 멱등성

**Validates: Requirements 1.6, 2.5**

같은 raw 응답으로 `--offline`을 두 번 실행한 `restaurants.json`은 바이트까지 같다.

### Property 8: 이동 시간 일치(메타모픽)

**Validates: Requirements 6.5, 6.7**

임의의 두 역에 대해 `get_transit_info(...).subway.minutes == return_options.subway_minutes(a, b, rule)`이고, `total_min == walk_to_station_min + subway.minutes + walk_from_station_min`이다.

### Property 9: 대칭성

**Validates: Requirements 6.5, 6.3**

장소 A, B에 대해 `subway.minutes`는 `get_transit_info(A, B)`와 `get_transit_info(B, A)`가 같다. `walk_to_station_min`과 `walk_from_station_min`은 서로 바뀐다.

### Property 10: 같은 역이면 0

**Validates: Requirements 6.6**

두 장소의 `nearest_station`이 같으면 `subway.same_station`이 `true`이고 `subway.minutes == 0`이다.

### Property 11: 환승역 일치

**Validates: Requirements 6.2**

모든 결과에서 `is_transfer_station == (len(lines) >= 2)`이고 `lines`는 `stations.json` 값과 같다.

### Property 12: ID 근거

**Validates: Requirements 8.4**

두 도구가 돌려주는 모든 `place_id`는 `places.json`에 있다.

### Property 13: 오류 형식

**Validates: Requirements 3.8, 5.5, 5.6, 8.2**

잘못된 입력(없는 `place_id`, 범위 밖 `radius_m`, 없는 역 이름)에서는 항상 `{"error": {"code", "message"}}` 한 개만 돌려주고 예외를 던지지 않는다.


## Error Handling

| 상황 | 도구 | 코드 |
|---|---|---|
| `places.json`에 없는 장소 | 둘 다 | `place_not_found` |
| Anchor가 아님 | restaurants | `restaurants_not_collected` |
| `radius_m`·`limit` 범위 밖 | restaurants | `invalid_argument` |
| 도착 인자 없음 | transit | `missing_argument` |
| 출발·도착 장소가 같음 | transit | `same_place` |
| 역 이름이 표에 없음 | transit | `station_not_found` |
| `nearest_station`이 `null`이거나 표에 없음 | transit | `no_station` |
| 파일을 읽을 수 없음·형식 오류 | 둘 다 | `data_unavailable` |
| 예기치 못한 오류 | 둘 다 | `internal_error`(`_safe`가 로그에 남김) |

- 수집 스크립트는 API 호출이 실패한 Anchor·언어를 검토 목록에 `api_error: ...`로 남기고 계속합니다. 키는 로그·오류 메시지에 남기지 않습니다(`fetch_places.request_json`과 같음).
- 로그는 한국어입니다.

## Testing Strategy

- `tests/test_restaurants.py`
  - 고정 응답으로 만든 작은 `restaurants.json`(임시 파일)으로 거리·정렬·`limit`·`total_in_radius`·경계 반경(정확히 같은 거리)을 확인합니다.
  - 실제 `restaurants.json`이 있으면 데모 Anchor 3곳이 모두 비어 있지 않은지(스모크), 모든 `restaurant_id`가 유일한지, 모든 Anchor가 `places.json`에 있는지 확인합니다.
  - 수집 순수 함수: 외국어 일치(exact·contains·불일치), `CUISINE_BY_CLASS`, 직렬화 왕복.
  - 수집 스크립트는 `monkeypatch`로 `request_json`을 고정 응답으로 바꿔 `--offline` 재현과 호출 수를 확인합니다. 실제 네트워크는 쓰지 않습니다(`socket`을 막는 기존 테스트 방식 참고).
  - 속성 테스트: Correctness Properties 1~7(Hypothesis를 이미 쓰는지 확인하고 없으면 `uv add --dev hypothesis`는 팀에 먼저 묻습니다, 열린 질문 7).
- `tests/test_transit.py`
  - 해운대 → 서면(`to_station="Seomyeon"`) 값을 `return_options`와 같은 `subway_minutes`로 검증합니다.
  - `to_place_id` 경로, 같은 역, 같은 장소, `OSIRIA`(해동용궁사), `nearest_station: null`, 환승역(서면), `to_station` 대소문자·공백, `to_station` 우선, `missing_argument`.
  - 속성 테스트: Correctness Properties 8~13.
- 모든 테스트는 `uv run pytest -q`에서 `USE_MOCK=1`, `FAKE_LLM=1`로 돌고 외부 API를 부르지 않습니다.
- 수동 확인: `uv run python -c "from app.tools.transit import get_transit_info; ..."`는 `@tool` 래퍼를 직접 부를 수 있습니다(`get_events`를 `return_options`가 그렇게 부름).

## 열린 질문

### 결정 (11/20, 팀 확정)

아래 결정이 이 문서의 다른 절이나 `requirements.md`와 다르면 결정이 우선합니다.

| # | 항목 | 결정 |
|---|---|---|
| 1 | 외국어 음식점 `contentTypeId` | 타입 필터 없이 받고, raw 응답으로 번호를 확인한 뒤 좁힌다 |
| 2 | `cuisine` | 필드를 유지한다. 실제 응답의 분류 코드로 표(`CUISINE_BY_CLASS`)를 채우고, 표에 없으면 `null` |
| 3 | `menu_raw` | 기준 장소(Anchor)마다 가장 가까운 5곳만 `detailIntro2`로 받는다. 나머지는 `null` |
| 4 | 서면역 주변 | `get_restaurants`에 선택 인자 `station`(`stations.json`의 역 이름)을 추가한다. `place_id`와 `station` 중 하나는 필수 |
| 5 | 거리 헬퍼 | `return_options.py`에 공개 거리 헬퍼를 추가하고 `transit.py`가 쓴다 |
| 6 | Pydantic 모델 위치 | `tools/restaurants.py` |
| 7 | Hypothesis | `pyproject.toml`에 없으면 추가하지 않고, 같은 속성을 일반 테스트(대표 예시 여러 개)로 확인한다 |
| 8 | 다른 공공 출처 | v1은 TourAPI만 쓴다 |
| 9 | steering 문서 | `data-rules.md` 「음식점」·「대중교통」 절은 B가 추가한다 |
| 10 | Anchor와 반경 | `haeundae-beach`, `jagalchi-market`, `gamcheon-village`, 서면역(`Seomyeon`). 수집 반경 500m |
| 11 | `walk_min` 경고 | 추가 경고 없음 (`distance: "straight_line_estimate"`로 충분) |

### 구현하면서 바뀐 것 (11/20, 실제 응답 확인 후)

결정과 실제 API 응답 때문에 위 본문과 달라진 부분입니다. 코드와 `data-rules.md`가 기준입니다.

- **국문 수집 API**: `locationBasedList2` 대신 `areaBasedList2`(`contentTypeId=39`, `lDongRegnCd=26`)로 부산 전체(510건, 6쪽)를 받아 기준 좌표에서 500m 이내만 고릅니다. `locationBasedList2`는 해운대해수욕장 500m에서 1건만 돌려줬고, 같은 범위에 `areaBasedList2`로는 11건이 있었습니다. 호출 수도 기준 수와 무관해집니다.
- **외국어 수집**: 타입 없이 받은 응답에서 외국어 음식점 타입이 82임을 확인했고(결정 1), 같은 이유로 `areaBasedList2`(`contentTypeId=82`, `lDongRegnCd=26`)를 언어별 1회 받습니다. 부산 전체에 언어별 18~19건뿐이라 43곳 중 4곳만 외국어 이름이 있습니다.
- **`cuisine` 표**: `KorService2/lclsSystmCode2`(`lclsSystm1=FD`) 응답으로 코드 이름을 확인해 채웠습니다. `FD020100`은 중식, `FD020300`이 서양식입니다.
- **`get_restaurants` 시그니처**: `get_restaurants(place_id=None, station=None, radius_m=500, limit=10)`. 둘 다 없으면 `missing_argument`, 둘 다 주면 `place_id` 우선, 역 이름이 표에 없으면 `station_not_found`. 응답에 `station` 필드가 추가됐습니다.
- **`radius_m` 상한**: 수집 반경이 500m라 500을 넘으면 `invalid_argument`입니다(요구사항 3.2의 1000 대신 파일의 `radius_m`까지).
- **파일 형식**: `station_anchors`(역 이름 → `restaurant_id` 목록)가 추가됐습니다. 시드는 `{"radius_m", "place_ids", "stations"}` 형식입니다.
- **호출 함수**: 따로 만들지 않고 `fetch_events.py`·`fetch_hours.py`처럼 `fp.OFFLINE`·`fp.REUSE_RAW`를 설정하고 `fp._call_and_save`를 씁니다.
- **`return_options.py` 공개 헬퍼**: `straight_km`(이름만 공개로 바꿈), `station_table`, `travel_rule`, `find_station`. `transit.py`와 `restaurants.py`가 씁니다.
- **검토 목록**: `restaurants_review.csv`는 BOM 없는 UTF-8입니다(`places_review.csv`는 엑셀용 BOM 있음).
- **장면 값**: 해운대해수욕장 → 서면역은 도보 10분 + 지하철 39분 = 49분입니다(본문 예시의 9분·48분은 어림값).

### 원래 질문 (결정 전 기록)

1. **외국어 서비스의 음식점 `contentTypeId`.** 국문은 39입니다. 영어·일본어·중국어 서비스의 음식점 번호(예상 82)가 실제와 같은지 확인이 필요합니다. 틀리면 타입 필터가 결과를 모두 막습니다. 초기에는 필터 없이 받고 확인 후 줄이는 안을 권합니다. 중국어 간체 서비스(`ChsService2`)는 신청 후 사용이라 응답이 없을 수 있습니다(`data-rules.md`).
2. **`cuisine` 분류.** TourAPI 음식점 분류 코드(`lclsSystm`)와 한식·양식 등 매핑 표를 실제 응답으로 확정해야 합니다. 확인 전에는 `null`을 허용합니다. `cuisine` 필드 자체가 필요한지 팀이 정합니다.
3. **`menu_raw`를 받을지.** `detailIntro2` 호출이 음식점 수만큼 필요합니다(Anchor 3곳 × 수십~수백 곳). 일일 한도와 시간 때문에 v1은 `null`로 두고, 필요하면 Anchor별 가까운 상위 N곳만 받는 안을 제안합니다.
4. **서면역 주변 음식점.** `places.json`에 서면 장소가 없어 `place_id` 기반 도구로는 조회할 수 없습니다. 선택지: (a) 도구에 선택 인자 `station`(역 표의 역 이름)을 추가해 역 좌표를 기준으로 조회, (b) `places.json`에 서면 장소를 팀이 추가(새 ID는 B가 만들지 않음), (c) 데모에서 제외. (a)를 권하되 도구 시그니처가 `get_restaurants(place_id, radius_m)`에서 바뀌므로 팀 확인이 필요합니다.
5. **`return_options`의 거리 함수 공개.** `transit.py`가 장소→역 거리를 계산할 때 비공개 `_straight_km`를 쓰지 않으려면 `return_options.py`에 공개 이름을 추가하거나 `fetch_places.haversine_m`을 쓰면 됩니다. 후자는 `scripts/`(A) 모듈을 도구가 import하는 방향이라 의존 방향이 어색합니다. 공개 헬퍼 추가(같은 B 파일)를 권합니다.
6. **Pydantic 모델 위치.** `RestaurantRecord`·`RestaurantTable`을 `backend/app/models/`(공용, 뼈대 담당 리뷰)가 아니라 `tools/restaurants.py`에 둡니다. 프론트엔드나 API가 이 형식을 직접 쓰게 되면 공용 모델로 옮겨야 합니다.
7. **Hypothesis 사용.** 속성 테스트에 `hypothesis`가 필요합니다. 이미 `pyproject.toml`에 있는지 확인하고, 없으면 의존성 추가를 팀에 먼저 알립니다.
8. **다른 공공 출처.** 후보로만 적습니다(확정은 팀). (a) 부산 공공데이터포털의 「부산맛집 정보」류 데이터셋, (b) 한국관광공사 「한국관광 데이터랩」, (c) 식품의약품안전처 위생등급 지정 음식점 정보(「모범음식점」). 식단(할랄·채식) 정보를 주는 공공 출처는 확인하지 못했습니다. 있으면 별도 spec으로 다룹니다. 외국어 이름과 좌표의 품질이 TourAPI와 같지 않을 수 있습니다.
9. **steering 문서 수정.** `.kiro/steering/data-rules.md`는 `team.md`가 아니라 공용 파일 목록에 없지만 팀 규칙 문서입니다. 「음식점」·「대중교통」 절을 B가 추가해도 되는지 확인합니다.
10. **Anchor 확장 시점.** 데모 3곳 외 장소(`places.json` 33곳 전체)를 받을지는 API 호출 수와 데모 필요에 따라 정합니다. 음식점 파일 크기(3곳 × 1000m 반경이면 수백 곳)가 Lambda 패키지·콜드스타트에 미치는 영향도 확인이 필요합니다.
11. **`walk_min`의 전제.** 음식점 도보 분은 직선거리 × 1.3 ÷ 4.5km/h 추정이며 길·경사를 반영하지 않습니다. 감천문화마을처럼 경사가 큰 곳에서는 실제보다 짧을 수 있습니다. 응답에 이미 `distance: "straight_line_estimate"`로 밝혔고, 추가 경고가 필요한지 팀이 정합니다.
