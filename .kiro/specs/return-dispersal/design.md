# 설계: 축제 후 귀가 분산 (return-dispersal)
요구사항은 `requirements.md`를 따릅니다. 이 문서에는 구성, 규칙, 반환 형식만 적습니다.

## 확정된 결정 (11/20)
| 항목 | 결정 |
|---|---|
| 다른 노선 역(c) | 범위에서 뺀다. 역 데이터에 동해선·경전철이 없다 |
| 혼잡 역 | 행사 `main_place_id`의 `nearest_station` 1개 |
| 도보 대안 역 상한 | 걸어서 20분 |
| 도착지 | `destination_station`(`busan_stations.csv`의 `name_en`), 기본값 `"Seomyeon"`(데모 숙소가 서면, 팀 확정). `destination_place_id`는 선택이며 주면 그 장소의 `nearest_station`을 도착역으로 쓴다. 둘 다 주면 `destination_station` 우선 |
| 이동 시간 | 도착지가 역이라 역 사이 시간이 필요하다. 카카오 대중교통 경로를 실시간으로 불러 쓰고(저장·캐시 금지), 실패하거나 `USE_MOCK=1`이면 역 좌표 기반 추정(기존 `travel_times`와 같은 규칙: 경로 거리 = 직선거리 × 1.3, 지하철 25km/h + 10분)으로 계산한다. 항목마다 `time_source`(`kakao`·`estimate`)로 밝히고 `basis`에도 적는다 |
| `main_place_id` | `fetch_events.py`가 `events.json`에 저장. `event_name`만 받으면 이것을 출발 장소로 쓴다 |
| 혼잡 시간대 | 종료 30분 전~60분 뒤. 규칙 기반 가정이며 `basis`와 docstring에 밝힌다 |
| 막차 | `shift_later`만 저장된 막차 표(`last_trains.json`)와 비교한다. 막차 뒤면 `last_train_missed`, 파일·값이 없으면 `last_train_unknown`. 막차 시각은 응답에 넣지 않는다 |

## 구성
```
backend/
  app/
    tools/return_options.py   get_return_options(@tool)와 순수 계산 함수 (새로 추가, B)
    tools/kakao_route.py      fetch_routes: 카카오 대중교통 경로 실시간 조회. 실패하면 None, 저장·캐시 없음
    ranking/routes.py         rank_routes: 제안에 점수를 매겨 이름 붙은 2~3안을 고른다 (ranked)
    tools/lookup.py           get_events 반환에 main_place_id 추가 (B, 필드 추가만)
    data/stations.json        역 표 (새로 추가, B). busan_stations.csv에서 만든다
    data/events.json          행사마다 main_place_id 추가 (fetch_events.py가 만든다)
    data/last_trains.json     역·방향·요일별 막차 시각 (fetch_last_trains.py가 만든다)
  scripts/build_stations.py   busan_stations.csv → app/data/stations.json (새로 추가)
  scripts/fetch_events.py     main_place_id 계산 추가 (B)
  scripts/fetch_last_trains.py  부산교통공사 열차시각표(_GW) → app/data/last_trains.json
  tests/test_fetch_last_trains.py     막차 수집 스크립트 (실제 API를 부르지 않음)
  tests/test_return_options.py        카카오 없이(전부 estimate) 동작하는 경우
  tests/test_return_options_kakao.py  카카오 성공·일부 실패·전부 실패·USE_MOCK (fetch_routes 를 mock)
  tests/conftest.py                   no_kakao: 모든 테스트에서 fetch_routes 를 None 으로 고정
  tests/test_lookup.py        get_events 반환의 main_place_id 검사 추가
```
- `lookup.py`는 이미 커서 도구를 새 파일에 둡니다. `return_options.py`는 `lookup.py`의 `_safe`, `LookupFailure`, `_load_json`, `_load_places`, `_parse_date`와 `get_events`의 계산을 불러 씁니다.
- `get_events`는 `@tool`이지만 그대로 부를 수 있어 `lookup.get_events(date=...)`를 직접 부릅니다(Guardian과 같은 방식). 오류 dict가 오면 같은 코드로 다시 알립니다.
- 계산은 `@tool`이 없는 `return_options(...)`에 있고, `get_return_options`는 이를 `@tool` + `@_safe`로 감싼 것입니다.
- 이동 시간은 `get_travel_time`(장소 사이 표)을 쓰지 않습니다. 도착지가 역이라 `return_options.py`가 역 좌표(`stations.json`)로 `kakao_route.fetch_routes`를 부르고, 결과가 없으면 같은 좌표와 `travel_times.json`의 `rule`로 직접 계산합니다.
- `get_events`에 필드를 추가해도 Guardian은 영향이 없습니다. `guardian/context.py`의 `Event` 모델은 `name`, `start`, `end`, `place_ids`만 읽고 모르는 필드는 무시합니다(`extra` 설정 없음, 구현 때 테스트로 확인).
- `guardian/`은 이 도구를 부르지 않습니다.

## 데이터
### `main_place_id` (`events.json`)
- `fetch_events.build_events`가 `place_ids`를 만들 때 쓰는 거리 계산을 그대로 써서, `place_ids` 중 행사 좌표와 직선거리가 가장 가까운 장소를 `main_place_id`로 둡니다. 거리가 같으면 `place_id` 사전순. `place_ids`가 비면 `null`.
- 그래서 `main_place_id`는 항상 `place_ids` 안에 있고(1km 이내), `places.json`에 있는 값입니다. 1km 밖의 장소는 대표 장소가 되지 않습니다.
- `--offline`은 저장된 응답에서 다시 만들므로 API를 부르지 않습니다.
- 현재 `events.json` 14개 행사로 확인한 값: 빛축제의 가장 가까운 장소는 `sea-life-busan`(약 0.05km)이고 `haeundae-beach`(약 0.11km)가 그다음입니다. 둘 다 `nearest_station`이 `Haeundae`라 장면 7 결과는 같습니다. 행사 1개는 `place_ids`가 비어 `null`이 됩니다.

### 역 표 `stations.json`
`busan_stations.csv`(부산 도시철도 1~4호선, 데이터 114행)에서 만듭니다. 환승역을 합쳐 108곳입니다. API를 부르지 않습니다.
```
{"note": "...", "stations": [{"station": "Haeundae", "name_ko": "해운대역", "lines": ["2"], "lat": 35.163672, "lng": 129.158908}]}
```
- `station`은 CSV의 `name_en`이며 `places.json`의 `nearest_station`과 같은 문자열입니다. 연결은 정확히 같은 문자열일 때만 합니다.
- 환승역(`name_en` 중복: Seomyeon, Yeonsan, Dongnae, Suyeong, Deokcheon, Minam)은 한 항목으로 합치고 `lines`에 노선을 모두 넣습니다. 좌표는 행들의 평균입니다. 도착역 기본값 `Seomyeon`은 1·2호선 두 행(좌표 평균 약 35.1580, 129.0593)이 한 항목이 됩니다. 역 표의 `lines`는 참고용이며 도구 출력에 넣지 않습니다. 노선·환승은 카카오 경로를 받은 항목의 `legs`·`transfers`로만 나옵니다.
- 도착역 입력은 `station` 값과 대소문자·앞뒤 공백을 무시하고 비교합니다. 응답에는 표의 `station` 값을 돌려줍니다.
- `places.json`의 `nearest_station` 중 표에 없는 값이 하나 있습니다(`OSIRIA`, 동해선). 스크립트가 경고로 출력합니다. `destination_place_id`로 정한 장소의 역이 이것이면 `no_station` 오류입니다.
- `places.json`의 좌표·가까운 역은 검증 전 값입니다(`data-rules.md`). 역을 사실로 단정하지 않습니다.

### 막차 표 `last_trains.json`
`scripts/fetch_last_trains.py`가 공공데이터포털 「부산교통공사_부산도시철도 열차시각표 조회 서비스_GW」에서 받아 만듭니다. 원본 응답은 `app/data/raw/_last_trains/`에 두고 이 파일에는 막차 시각만 저장합니다. 도구는 이 파일만 읽고 API를 부르지 않습니다.
```
{"source": {"provider": "부산교통공사", "api": "...", "service": "...", "fetched_at": "2026-11-20", "day_codes": {...}, "note": "..."},
 "stations": {"Haeundae": {"scode": "203", "toward": "Seomyeon", "updown": 1,
                           "last_train": {"1": "23:29", "2": "23:29", "3": "23:29"}}}}
```
- 저장하는 역·방향은 네 개입니다: `Haeundae`·`Dongbaek`·`Jung-dong` → `Seomyeon`, `Seomyeon` → `Haeundae`(모두 2호선). 역마다 방향(`toward`)은 하나입니다.
- `last_train`의 키는 요일 코드입니다(`1` 평일, `2` 토요일, `3` 일요일·공휴일). 값은 "HH:MM"이며 자정을 넘는 막차는 24시 이상으로 적습니다(예: `24:05`). 조건에 맞는 열차가 없는 요일은 키를 넣지 않습니다(지어내지 않음).
- 목적지 전에 끝나는 열차는 막차로 보지 않습니다. 값은 표준 열차 도착시각이라 실제와 다를 수 있습니다.
- 도구가 읽는 방법(`return_options.last_train_warnings`): `stations[혼잡 역]`의 `toward`가 도착역과 같을 때만 `last_train[요일 코드]`를 씁니다. 요일 코드는 행사 날짜의 요일로 정하고(토 `2`, 일 `3`, 그 외 `1`), 공휴일 달력이 없어 평일 공휴일은 평일로 봅니다. 막차 시각은 행사 날짜 00:00에 시·분을 더한 값입니다.
- 파일이 없거나, 역 행이 없거나, 방향이 다르거나, 요일 값이 없거나, 형식이 틀리면(시 0~47, 분 0~59 밖) 막차를 모르는 것으로 봅니다(`last_train_unknown`). 도구 오류로 만들지 않습니다.

### 이미 있는 데이터
- 행사: `get_events(date)`. 11/28 빛축제는 `start` 18:00, `end` 23:00. 11/28 외 날짜는 개막일 규칙 때문에 나오지 않습니다.
- 이동 시간 추정 규칙: `travel_times.json`의 `rule`(`route_factor` 1.3, `walk_kmh` 4.5, `subway_kmh` 25, `subway_overhead_min` 10). 값은 이 파일에서 읽어 쓰므로 `get_travel_time`과 어긋나지 않습니다. 역 사이 시간은 이 표에 없어 새로 계산합니다.
- 도착역 기본값 `Seomyeon`은 `busan_stations.csv`의 `name_en`과 같습니다(1·2호선, 2행). `places.json`에서 `nearest_station`이 `Seomyeon`인 장소는 지금 없지만 도착역에는 영향이 없습니다.

## 기준값 (`return_options.py` 상단 상수)
리허설 전에 데모 데이터로 맞추고 고정합니다.
| 이름 | 값 | 뜻 |
|---|---|---|
| `STATION_CROWD_BEFORE_MIN` | 30 | 행사 종료 몇 분 전부터 혼잡으로 보는지 |
| `STATION_CROWD_AFTER_MIN` | 60 | 행사 종료 몇 분 뒤까지 혼잡으로 보는지 |
| `EARLY_LEAVE_BEFORE_END_MIN` | 40 | `shift_earlier` 출발 시각. 혼잡 시작보다 10분 이르게 한다 |
| `WALK_ALT_MAX_MIN` | 20 | 다른 역까지 걷는 시간 상한 |
| `MAX_OPTIONS` | 5 | 제안 최대 개수 |
| `DEFAULT_DESTINATION_STATION` | `"Seomyeon"` | 도착역 기본값(데모 숙소가 서면). 숙소가 바뀌면 이 값만 바꾼다 |
혼잡 시간대(30·60분)는 실측이 아니라 가정입니다. 근거를 묻는 질문에는 "규칙으로 정한 값"이라고 답합니다.

## 도구
```
get_return_options(date, place_id=None, event_name=None, destination_station=None,
                   destination_place_id=None, planned_departure=None) -> dict
```
- `destination_station`의 기본값은 `None`이고, 둘 다 `None`이면 `DEFAULT_DESTINATION_STATION`(`"Seomyeon"`)을 씁니다. 함수 인자 기본값을 `"Seomyeon"`으로 두면 "생략"과 "직접 서면을 지정"을 구별할 수 없어 `destination_place_id`와 겹칠 때 우선순위를 정할 수 없습니다. 모델이 읽는 docstring에는 "기본값은 Seomyeon"이라고 적습니다.
- 도착역 결정 순서: `destination_station` → `destination_place_id`의 `nearest_station` → 기본값. 앞의 것이 있으면 뒤의 것은 검증하지 않습니다.
- `@tool` + `@_safe`. docstring은 영어로 쓰고(`team.md`, `tech.md`) 아래를 모두 적습니다.
  - 언제 쓰는지: 행사 종료 뒤 귀가 방법을 물을 때
  - 입력과 출력
  - 역 혼잡은 규칙 기반 추정이며 실시간·실측 혼잡이 아니다
  - 혼잡 시간대(종료 30분 전~60분 뒤)는 근거 데이터 없이 정한 가정이다
  - 이동 시간은 카카오 실시간 대중교통 경로를 우선하고, 없으면 역 좌표로 어림한 값이다(둘 다 장소에서 역까지 걷는 시간 제외). 카카오 결과는 저장·캐시하지 않는다
  - `time_source`가 `kakao`이면 `route_type`, `transfers`, `fare`, `walk_meters`, `legs`는 카카오 값이다. `estimate`이면 노선·환승을 지어내지 않는다
  - 막차 경고는 저장된 표준 시간표에 해당 역·방향이 있을 때만 쓰며 실제 열차 시각과 다를 수 있다. `shift_later`는 출발이 막차 뒤면 `last_train_missed`, 막차 뒤가 아니면 막차 경고 없음, 맞는 시간표가 없으면 `last_train_unknown`이다. 두 경고 모두 실시간 시간표를 확인하라고 안내한다
  - `legs`의 `from_names`·`to_names`에 사용자 언어가 있으면 그 이름을, 없으면 한국어 이름을 그대로 쓴다. 승하차 이름을 번역하거나 지어내지 않는다
  - "expected to be crowded", "about N minutes"로 말한다
  - 도착역 기본값은 `Seomyeon`(데모 숙소 기준)이다. 사용자가 다른 도착지를 말하면 `destination_station`(영문 역 이름) 또는 `destination_place_id`로 넘긴다
- `place_id`·`event_name`이 둘 다 없으면 `missing_argument` 오류입니다.
- 에이전트가 사용자의 도착역을 영문 이름(`name_en`)으로 알면 `destination_station`, 장소만 알면 `destination_place_id`(`places.json`에 있는 장소만)로 넘깁니다.

## 처리 순서
1. `date` 검증, `place_id` 검증(`places.json`). 도착역 결정(요구사항 2.5): `destination_station`이 있으면 역 표에서 찾고(없으면 `station_not_found`), 없고 `destination_place_id`가 있으면 그 장소의 `nearest_station`(`place_not_found`·`no_station`), 둘 다 없으면 기본값.
2. `get_events(date)`에서 행사 찾기(요구사항 2.2~2.3). 행사 `start`·`end`가 00:00:00·23:59:59면 `no_time_basis`.
3. 출발 장소 정하기(요구사항 2.4). 혼잡 역 = 행사 `main_place_id`의 `nearest_station`. 없거나 역 표에 없으면 `no_event_station`. 출발 장소의 역을 `stations.json`에서 찾고, 없으면 `no_station`. 도착역이 혼잡 역 또는 출발 장소의 역과 같으면 `same_station`.
4. 혼잡 시간대 = `[end − 30분, end + 60분)`. 자정을 넘을 수 있어 날짜가 있는 시각으로 계산합니다.
5. 기준 출발 결정(요구사항 2.8). `planned_departure` 형식이 틀리면 `invalid_time`.
6. `baseline.congested` = 기준 출발이 혼잡 시간대 안 **그리고** 출발 장소의 역이 혼잡 역. 아니면 `options: []`로 끝. `baseline.minutes`는 이 경우에도 계산해 돌려줍니다(출발 장소의 역 → 도착역).
7. 제안 만들기:
   - (a) 시각: 출발 역은 그대로, 출발 시각을 `end − 40분`, `end + 60분`으로. `end − 40분`이 행사 시작보다 늦지 않으면 `shift_earlier`는 만들지 않습니다.
   - (a) `shift_later`의 `warnings`는 `last_train_warnings(행사 날짜, 혼잡 역, 도착역, end + 60분)`의 결과입니다(「막차 표」): 막차 뒤면 `["last_train_missed"]`, 막차 이전이면 `[]`, 표에서 찾지 못하면 `["last_train_unknown"]`. 다른 제안과 `baseline`은 막차와 비교하지 않습니다.
   - (b) 걸어서 다른 역: 혼잡 역이 아니고, 혼잡 역에서 걸어서 20분 이내인 역(노선 무관), 가까운 순.
8. 역 사이 시간 정하기: 기준 출발 역과 제안의 이용 역마다 카카오 경로를 조회하고(아래 「카카오 실시간 경로」), 결과가 없는 역은 추정 시간을 씁니다.
9. (b)의 `extra_min` = (혼잡 역→이용 역 도보 + 이용 역→도착역 시간) − `baseline.minutes`. 이용 역이 도착역이면 추정 시간 0. (a)는 출발 역이 같아 0입니다.
10. 정렬·상한 적용(요구사항 4.9). 카카오 값으로 바뀐 `extra_min` 기준입니다.
11. `ranked` = `rank_routes(결과)`(아래 「반환 형식」). `options`가 비면 `ranked`도 빈 목록입니다.

### 이동 시간 계산
역 사이 시간은 카카오 실시간 경로를 우선하고, 없으면 역 좌표 기반 추정을 씁니다. 걷는 시간(`walk_min`)은 항상 추정입니다.

#### 카카오 실시간 경로 (`time_source: "kakao"`)
- `kakao_route.fetch_routes(출발 역 좌표, 도착역 좌표)`가 돌려준 경로 중 첫 경로를 씁니다. 시간은 `total_minutes`이고, `route_type`, `transfers`, `distance_m`, `fare`, `walk_meters`, `legs`를 `baseline`·`options` 항목에 그대로 넣습니다.
- 도구 호출 한 번에 출발 역마다 한 번씩만 조회합니다(기준 출발 역 + 이용 역, 같은 역은 한 번). 서로 다른 역은 스레드로 동시에 조회합니다. 조회마다 3초 제한, 재시도 없음이라 전체도 3초대에 끝납니다.
- `USE_MOCK=1`이거나 `KAKAO_REST_API_KEY`가 없으면 조회하지 않습니다(네트워크 0회).
- 조회 실패(`None`, 예외, 첫 경로 형식 오류)는 오류가 아닙니다. 그 역만 추정으로 대체하므로 한 응답에 `kakao`와 `estimate`가 섞일 수 있습니다.
- 결과는 그 호출 안의 지역 변수로만 쓰고 파일·DB·전역 변수·메모리 캐시에 저장하지 않습니다.

#### 역 좌표 기반 추정 (`time_source: "estimate"`)
- 경로 거리 = 두 역 좌표의 직선거리 × `route_factor`(1.3).
- 지하철 시간(분) = 올림(경로 거리 / `subway_kmh`(25) × 60 + `subway_overhead_min`(10)).
- 도보 시간(분) = 올림(경로 거리 / `walk_kmh`(4.5) × 60).
- 상수는 `travel_times.json`의 `rule`을 읽어 씁니다(기존 이동 시간 표와 어긋나지 않게). 파일을 못 읽으면 `data_unavailable`입니다.
- `basis`에 이 규칙 값과 "카카오 실시간 경로 우선, 없으면 역 좌표 기반 추정, 장소↔역 도보 제외, 카카오 결과 저장·캐시 없음"을 적습니다.
- 환승역(서면)은 1·2호선 좌표 평균 한 점으로 계산합니다. 추정에서는 환승 시간이 규칙의 고정 10분에 들어 있다고 보며, 환승 여부는 단정하지 않습니다. 카카오 경로를 받은 경우에만 `transfers`·`legs`로 환승을 말합니다.

### 장면 7 어림값 (역 좌표로 계산한 추정. 카카오가 없을 때의 값)
출발 해운대역, 도착 서면역:
| 이용 역 | 도보 | 역→서면 지하철 | 기준(해운대→서면 39분) 대비 `extra_min` |
|---|---|---|---|
| 해운대 (시각만 변경) | 0 | 39 | 0 |
| 동백 | 18 | 36 | +15 |
| 중동 | 17 | 42 | +20 |
장산역(약 31분)과 시립미술관역(약 34분)은 도보 20분을 넘어 빠집니다. 동백역은 서면 쪽이라 지하철이 3분 줄어 중동역보다 `extra_min`이 작습니다. 이 값은 노선·방향을 반영하지 않은 거리 추정입니다.

## 반환 형식
Guardian·프론트가 필드를 그대로 쓰도록 평평한 dict로 돌려줍니다. 시각은 `+09:00` ISO 문자열이며 자정을 넘으면 다음 날 날짜가 붙습니다.
```
{
  "date": "2026-11-28",
  "basis": {"kind": "rule", "measured": false,
            "assumed_window": {"before_end_min": 30, "after_end_min": 60},
            "travel_time_rule": {"route_factor": 1.3, "subway_kmh": 25, "subway_overhead_min": 10, "walk_kmh": 4.5},
            "note": "Rule-based estimate, not measured or real-time crowding. The crowded window (30 min before to 60 min after the event end) is an assumption. Travel times use live Kakao public-transit routes when available and otherwise fall back to estimates from station coordinates; they exclude walking to and from places. Kakao route results are not stored or cached. Last-train warnings use the stored Busan Metro standard timetable when the requested station and direction are available; actual train times can differ."},
  "event": {"name": "해운대 빛축제", "start": "...T18:00:00+09:00", "end": "...T23:00:00+09:00", "main_place_id": "sea-life-busan"},
  "origin": {"place_id": "sea-life-busan", "station": "Haeundae"},
  "destination": {"station": "Seomyeon", "place_id": null, "is_default": true},
  "congested_station": {"station": "Haeundae", "main_place_id": "sea-life-busan",
                        "from": "...T22:30:00+09:00", "to": "2026-11-29T00:00:00+09:00"},
  "baseline": {"depart_at": "...T23:00:00+09:00", "station": "Haeundae", "congested": true,
               "minutes": 39, "mode": "subway", "time_source": "estimate"},
  "options": [
    {"type": "shift_earlier", "depart_at": "...T22:20:00+09:00", "station": "Haeundae", "walk_min": 0,
     "extra_min": 0, "avoids_congestion": true, "warnings": ["leaves_before_event_end"], "time_source": "estimate"},
    {"type": "shift_later", "depart_at": "2026-11-29T00:00:00+09:00", "station": "Haeundae", "walk_min": 0,
     "extra_min": 0, "avoids_congestion": true, "warnings": ["last_train_missed"], "time_source": "estimate"},
    {"type": "walk_to_station", "depart_at": "...T23:00:00+09:00", "station": "Dongbaek", "walk_min": 18,
     "extra_min": 15, "avoids_congestion": true, "warnings": [], "time_source": "estimate"},
    {"type": "walk_to_station", "depart_at": "...T23:00:00+09:00", "station": "Jung-dong", "walk_min": 17,
     "extra_min": 20, "avoids_congestion": true, "warnings": [], "time_source": "estimate"}
  ],
  "ranked": [
    {"option": {"type": "walk_to_station", "station": "Dongbaek", ...}, "score": -63.0, "travel_min": 54,
     "arrive_at": "...T23:54:00+09:00",
     "breakdown": {"travel": 54.0, "early": 0.0, "wait": 0.0, "walk": 9.0, "penalty": 0.0},
     "labels": ["best"], "excluded": null},
    {"option": {"type": "walk_to_station", "station": "Jung-dong", ...}, "score": -67.5, "travel_min": 59,
     "arrive_at": "...T23:59:00+09:00",
     "breakdown": {"travel": 59.0, "early": 0.0, "wait": 0.0, "walk": 8.5, "penalty": 0.0},
     "labels": [], "excluded": null},
    {"option": {"type": "shift_earlier", "station": "Haeundae", ...}, "score": -79.0, "travel_min": 39,
     "arrive_at": "...T22:59:00+09:00",
     "breakdown": {"travel": 39.0, "early": 40.0, "wait": 0.0, "walk": 0.0, "penalty": 0.0},
     "labels": ["earliest_arrival", "least_walking"], "excluded": null}
  ]
}
```
- 위 숫자는 카카오가 없을 때(전부 `estimate`)의 값이며 「장면 7 어림값」과 같습니다. 카카오 경로를 받으면 `minutes`·`extra_min`·`ranked`가 그 값으로 바뀝니다.
- 위 예에서 `shift_later`(11/29 00:00 출발)는 저장된 해운대 → 서면 토요일 막차(23:29)보다 늦어 `last_train_missed`이고, 그래서 `ranked`에 없습니다.
- `time_source`: `baseline`과 `options` 항목마다 `"kakao"` 또는 `"estimate"`. `"kakao"`인 항목에는 카카오 첫 경로의 요약이 더 붙습니다. `"estimate"`인 항목에는 이 필드들이 없습니다.
  ```
  "route_type": "SUBWAY" | "BUS" | "BUS_AND_SUBWAY", "transfers": 0, "distance_m": 16000, "fare": 1600 (없으면 null),
  "walk_meters": 0,
  "legs": [{"mode": "SUBWAY", "minutes": 40, "distance_m": 16000, "lines": ["2호선"], "from_name": "해운대", "to_name": "서면",
            "from_names": {"ko": "해운대", "en": "Haeundae"}, "to_names": {"ko": "서면", "en": "Seomyeon"}}]
  ```
  - `from_name`·`to_name`은 카카오가 준 한국어 승하차 이름입니다. 카카오가 준 구간 값은 그대로 두고 `from_names`·`to_names`만 덧붙입니다.
  - `from_names`·`to_names`는 `{언어: 이름}`이며 데이터에 있는 언어만 넣습니다(장소의 `names`와 같은 방식). `ko`는 카카오 이름 그대로입니다. `en`은 `mode`가 `SUBWAY`인 구간에서 이름의 '역'을 떼고 역 표의 `name_ko`와 맞을 때만 역 표의 `station` 값을 넣습니다. 역 표에는 한국어·영어만 있어 다른 언어는 나오지 않습니다.
  - 버스 정류장과 역 표에 없는 역은 `{"ko": ...}`만, 이름이 없는 구간(도보)은 `{}`입니다. 이름을 번역하거나 만들지 않습니다.
- `ranked`: `rank_routes`(`app/ranking/routes.py`)가 `options`를 채점해 점수 높은 순으로 돌려준 2~3안입니다. `options`는 그대로 두고(순서 없는 제안 목록, `extra_min` 순) 추천 순서는 `ranked`로 봅니다.
  - 항목: `option`(`options` 항목 그대로), `score`(비용을 분으로 환산해 음수로 둔 값, 높을수록 좋음), `travel_min`(`baseline.minutes + extra_min`), `arrive_at`(`depart_at + travel_min`), `breakdown`(`travel`, `early`, `wait`, `walk`, `penalty`), `labels`, `excluded`.
  - `labels`: `best`(점수 1위), `earliest_arrival`(도착역에 가장 빨리 닿는 안), `least_walking`(가장 덜 걷는 안). 한 안이 여러 이름을 가질 수 있고, 이름 붙은 안을 먼저 넣은 뒤 남은 자리(최대 3안)를 점수 순으로 채웁니다. 동점은 `options` 순서입니다.
  - 막차를 놓치는 안(`warnings`에 `last_train_missed`)은 `ranked`에서 뺍니다. `options`에는 남습니다. `ranked`에 들어간 항목의 `excluded`는 `null`입니다.
  - 가중치는 `app/ranking/weights.py`의 `ROUTE_*`입니다. `options`가 비면 `ranked`도 빈 목록입니다.
- `destination.place_id`는 `destination_place_id`로 도착역을 정했을 때만 값이 있고, 그 밖에는 `null`입니다. `is_default`는 기본값을 썼을 때만 `true`입니다.
- `type`: `shift_earlier`, `shift_later`, `walk_to_station`. `warnings`: `leaves_before_event_end`(`shift_earlier`), `last_train_missed` 또는 `last_train_unknown`(`shift_later`, 막차 이전이면 빈 목록).
- `ratio`, 혼잡 등급, 집중률 같은 필드는 두지 않습니다.
- 오류: `{"error": {"code", "message"}}`. 코드: `invalid_date`, `invalid_time`(`planned_departure`가 HH:MM이 아님), `place_not_found`, `missing_argument`, `event_not_found`, `ambiguous_event`, `no_time_basis`, `no_event_station`, `station_not_found`(`destination_station`이 역 표에 없음), `no_station`(`destination_place_id`의 장소 또는 출발 장소에 쓸 수 있는 역이 없음), `same_station`(도착역이 혼잡 역 또는 출발 장소의 역), `data_unavailable`.
- 출처 표기: 도구는 `sources`를 돌려주지 않습니다. 다른 조회 도구처럼 `app/chat/answer.py`가 도구 이름으로 조립합니다.

## 에이전트·프론트에서 쓰는 방법
- LLM은 `options`·`ranked`의 값(시각, 역 이름, 분)만 말합니다. 추천 순서와 이름(`labels`)은 `ranked`를 따릅니다. 역 혼잡을 "붐빈다"고 단정하지 않고 "행사가 끝나는 시간대라 붐빌 것으로 예상된다"로 말합니다(프롬프트 문구는 D가 정합니다).
- `destination.is_default`가 `true`면 "서면역 기준으로 계산했다, 다른 곳이면 알려 달라"고 안내합니다.
- 분은 "약 N분"으로 말하고, 장소에서 역까지 걷는 시간이 빠진 값이라는 점을 알립니다. 노선·환승은 `time_source`가 `kakao`인 항목에서만 `legs`·`transfers` 값으로 말하고, `estimate`인 항목에서는 단정하지 않습니다.
- 승하차 이름은 `from_names`·`to_names`에 사용자 언어가 있으면 그 이름을, 없으면 한국어 이름을 그대로 말합니다. 번역하거나 지어내지 않습니다.
- `last_train_missed`·`last_train_unknown`이 있으면 실시간 시간표를 확인하라고 안내합니다. 막차 시각은 응답에 없으므로 말하지 않습니다.
- 프론트는 `congested_station`과 `options`로 카드를 그릴 수 있습니다. 화면에 `basis.note`를 함께 보여 줍니다.

## 검증
테스트는 `backend/tests/test_return_options.py`, `tests/test_return_options_kakao.py`, `tests/test_lookup.py`. 실행: `uv run pytest -q tests/test_return_options.py tests/test_return_options_kakao.py tests/test_lookup.py`.
`tests/conftest.py`의 `no_kakao`가 모든 테스트에서 `return_options.fetch_routes`를 `None`으로 고정하므로, 셸에 키가 있어도 실제 호출이 나지 않습니다. 카카오 성공은 `test_return_options_kakao.py`가 `fetch_routes`를 직접 만든 경로로 바꿔 확인합니다(실제 응답을 복사하지 않음).
- `main_place_id`: `events.json`의 모든 행사에서 `place_ids`가 비면 `null`, 아니면 `place_ids` 안에 있는 값인지. `get_events` 반환에 들어 있는지. Guardian `build_context` 테스트가 그대로 통과하는지.
- 11/28 해운대 빛축제, `event_name`만 입력(출발 장소 = `main_place_id`)과 `place_id` 입력 두 경로.
- 도착역 결정: 생략하면 `Seomyeon`과 `is_default: true`, `destination_station="seomyeon "`(대소문자·공백)이 `Seomyeon`으로 정규화, `destination_place_id`만 주면 그 장소의 `nearest_station`과 `place_id` 값, 둘 다 주면 `destination_station` 우선(`destination_place_id`가 잘못된 ID여도 오류 없음), 역 표에 없는 이름 → `station_not_found`, `nearest_station`이 `null`인 장소 → `no_station`, 혼잡 역과 같은 도착역 → `same_station`.
- 이동 시간(카카오 없음): `baseline.minutes`와 (b)의 `extra_min`이 「장면 7 어림값」과 같은지(해운대→서면 39분, 동백 +15, 중동 +20), 규칙 상수를 `travel_times.json`의 `rule`에서 읽는지, `basis`에 규칙 값이 들어 있는지. 이용 역이 도착역이면 지하철 0분.
- 혼잡 역이 1개뿐인지(다른 행사 장소의 역은 혼잡 역이 아님). 출발 장소의 역이 혼잡 역이 아니면 `options: []`.
- 도보 20분 상한: 후보가 상한 이내인 역뿐이고 혼잡 역이 빠지는지.
- 혼잡 시간대 경계(22:30 포함, 24:00 제외), 자정 넘김.
- 진행 시간을 모르는 행사 → `no_time_basis`. 행사 없는 날짜 → `event_not_found`. `place_ids`가 빈 행사 → `no_event_station`.
- `other_line` 같은 제안 유형이 나오지 않는지. `basis.measured`가 `false`이고 `ratio` 필드가 없는지.
- 응답에 있는 모든 장소 ID·역 이름이 `places.json`·`stations.json`에 있는지.
- 카카오 없음 확인: `fetch_routes`가 `None`이면 `baseline`·`options`·`ranked`의 `time_source`가 전부 `estimate`이고 `legs` 등 경로 상세 필드가 없는지, 네트워크(`urllib`, 소켓)와 현재 시각을 막은 상태에서 `USE_MOCK` 값과 무관하게 같은 결과가 나오는지(네트워크 0회), `USE_MOCK=1`이면 실제 `fetch_routes`를 끼워도 네트워크를 타지 않는지 확인합니다.
- 저장 금지 확인: 저장하는 역 표와 스크립트(`build_stations.py`, `stations.json`)에 `kakao` 문자열·API 주소가 없는지 검사합니다.
- 카카오 성공(`test_return_options_kakao.py`): 출발 역마다 한 번씩 동시에 조회하는지, `baseline`·`options`에 `time_source: "kakao"`와 `legs`가 붙고 `extra_min`이 카카오 분으로 계산되는지, 일부 역만 실패하면 그 역만 `estimate`인지, 전부 실패하면 추정값과 같은지, `USE_MOCK=1`이면 `fetch_routes`를 부르지 않는지.
- 막차(`test_return_options.py`): 막차 뒤 출발이면 `last_train_missed`, 막차 이전이면 경고 없음, 방향(`toward`)이 다르거나 `last_trains.json`이 없으면 `last_train_unknown`. 수집 스크립트는 `tests/test_fetch_last_trains.py`가 실제 API 없이 확인합니다(없는 요일 값은 지어내지 않음, 자정 넘는 막차는 24시 이상).
- 승하차 이름(`test_return_options_kakao.py`): 지하철 구간의 역은 `ko`·`en`, 버스 정류장은 `ko`만, 도보 구간은 `{}`이고 `ko`·`en` 밖의 언어가 없는지.
- `planned_departure` 형식 오류 → `invalid_time`.
- `ranked`: 손으로 적은 기대 결과를 `rank_routes`에 넣은 값과 같은지, 순서와 `labels`(동백 `best` → 중동 → 해운대 `shift_earlier`가 `earliest_arrival`·`least_walking`), 막차를 놓치는 `shift_later`가 빠지는지, `options`가 비면 빈 목록인지.

## 연결 (이 spec의 범위 밖, 수정안만 제시)
- 에이전트 도구 목록 등록: `agent.py`는 A 담당입니다("tools 목록에 `get_return_options` 추가").
- `get_events` 반환 형식 표: `.kiro/specs/chat-agent/design.md` 「조회 도구 반환 형식」의 `get_events` 행에 `main_place_id` 추가(A·B가 정함).
- `data-rules.md` 「행사」: `main_place_id` 설명 한 줄과 역 표(`stations.json`, `build_stations`) 항목 추가. 이 문서는 구현 PR에서 B가 함께 고칠지 팀이 정합니다.
- REST 경로나 응답 모델이 필요해지면 `models/`, `api-contract.md`, `handler.py`는 공용 파일입니다. 사람이 요청하고 PR로 올립니다.
- 데모 점검표(`docs/demo-readiness.md` 장면 7) 상태 갱신은 구현 후 확인한 값으로 합니다.

## 남은 확인
1. 데모 숙소(서면)가 바뀌면 `DEFAULT_DESTINATION_STATION`만 바꿉니다. 서면은 환승역(1·2호선)이라 역 표에서 두 행의 평균 좌표를 쓰는데, 이 어림이 데모 문구에 영향이 없는지 리허설에서 봅니다.
2. 도보 20분에서 후보는 중동·동백입니다. 이 두 역은 해운대역과 같은 2호선이라 "다른 노선" 효과는 없습니다. 데모 대본 문구는 "한 정거장 걸어서 다른 역 이용"으로 맞춥니다.
3. 혼잡 시간대(30·60분)와 `EARLY_LEAVE_BEFORE_END_MIN`은 리허설에서 보고 조정할 수 있는 가정값입니다.
