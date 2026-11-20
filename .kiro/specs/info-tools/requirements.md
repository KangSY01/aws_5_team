# Requirements Document

기능 이름: 맛집·대중교통 정보 도구 (info-tools)

담당: B (데이터·도구). 노션 타임테이블 3순위 「맛집·축제·대중교통 정보 도구」 중 맛집과 대중교통입니다. 축제는 `get_events`가 이미 제공하므로 이 spec의 범위가 아닙니다.

## Introduction

조회 도구 2개를 `backend/app/tools/`에 추가합니다. 둘 다 LLM을 쓰지 않는 순수 파이썬이며, 대화 에이전트는 결과를 받아 문장만 만듭니다.

- `get_restaurants`: 장소 주변의 음식점을 찾습니다. 한국관광공사 TourAPI 음식점 정보를 미리 받아 `backend/app/data/restaurants.json`에 저장해 두고, 도구는 이 파일만 읽습니다(API 일일 한도 때문).
- `get_transit_info`: 두 장소(또는 장소와 역) 사이의 가까운 역, 호선, 역까지 도보 분, 지하철 이동 추정 분, 환승역 여부를 돌려줍니다. `stations.json`과 `travel_times.json`의 규칙을 다시 씁니다.

두 도구 모두 데이터에 없는 값(식단 정보, 실시간 도착, 시간표, 동해선 역)을 주장하지 않습니다. 이동 시간은 좌표로 계산한 추정이며 응답의 `basis`에 그렇게 적습니다.

## Glossary

- **Restaurant_Collector**: 음식점을 받아 `restaurants.json`을 만드는 스크립트 `backend/scripts/fetch_restaurants.py`
- **Restaurant_Table**: 수집 결과 파일 `backend/app/data/restaurants.json`
- **Restaurants_Tool**: Strands `@tool` 함수 `get_restaurants` (`backend/app/tools/restaurants.py`)
- **Transit_Tool**: Strands `@tool` 함수 `get_transit_info` (`backend/app/tools/transit.py`)
- **Anchor**: 음식점을 모아 둔 기준 장소. `places.json`의 `place_id` 하나이며, 그 좌표에서 반경 1000m 안을 수집합니다
- **Restaurant_ID**: 음식점의 식별자 `kto-<국문 contentid>`. `places.json`의 `place_id`가 아니며 장소 ID로 쓰지 않습니다
- **Station_Table**: `backend/app/data/stations.json`
- **Travel_Rule**: `travel_times.json`의 `rule`(경로 거리 = 직선거리 × 1.3, 도보 시속 4.5km, 지하철 평균 시속 25km + 10분, 분은 올림)
- **Transfer_Station**: Station_Table에서 `lines`가 2개 이상인 역
- **Error_Result**: `{"error": {"code": str, "message": str}}` 형식의 실패 결과

## Requirements

### Requirement 1: 음식점 수집

**User Story:** As a 데이터 담당자, I want TourAPI 음식점을 한 번 받아 저장하고 싶다, so that 도구가 API 한도와 상관없이 같은 결과를 돌려준다.

#### Acceptance Criteria

1. WHEN Restaurant_Collector가 실행되면, THE Restaurant_Collector SHALL 시드 파일에 적힌 각 Anchor의 좌표를 중심으로 반경 1000m 안의 국문 음식점(`KorService2/locationBasedList2`, `contentTypeId=39`)을 받는다
2. WHEN 국문 음식점의 외국어 이름을 찾을 때, THE Restaurant_Collector SHALL `fetch_places.py`와 같은 일치 규칙(한글·숫자 정규화 값이 같으면 exact, 국문 좌표 300m 이내에서 짧은 쪽이 3글자 이상 포함되면 contains)을 영어·일본어·중국어 간체·중국어 번체 서비스 결과에 적용한다
3. IF 어떤 언어에서 일치하는 항목이 없으면, THEN THE Restaurant_Collector SHALL 그 언어의 이름을 비워 두고 사람이 검토할 수 있게 검토 목록에 사유와 함께 남긴다
4. THE Restaurant_Collector SHALL 모든 외부 API 호출에 타임아웃 5초와 재시도 1회를 적용한다
5. THE Restaurant_Collector SHALL API 원본 응답을 `backend/app/data/raw/restaurants/` 아래에 저장하고 `serviceKey`는 저장하지 않는다
6. WHERE `--offline` 옵션이 주어지면, THE Restaurant_Collector SHALL 외부 API를 호출하지 않고 저장된 원본 응답으로 Restaurant_Table을 다시 만든다
7. WHERE `--reuse-raw` 옵션이 주어지면, THE Restaurant_Collector SHALL 같은 요청의 저장된 응답이 있는 요청은 다시 호출하지 않는다
8. IF 환경 변수 `DATA_GO_KR_KEY_DECODING`이 비어 있고 `--offline`이 아니면, THEN THE Restaurant_Collector SHALL 오류 메시지를 출력하고 종료 코드 1로 끝난다
9. THE Restaurant_Collector SHALL 시드의 Anchor를 `places.json`에 있는 `place_id`로만 지정한다
10. WHEN Restaurant_Collector가 끝나면, THE Restaurant_Collector SHALL 저장한 음식점 수, Anchor별 음식점 수, 검토가 필요한 항목 수, 실제 API 호출 수를 출력한다

### Requirement 2: 음식점 파일 형식

**User Story:** As a 도구 개발자, I want 음식점 파일 형식을 고정하고 싶다, so that 수집 스크립트와 도구가 같은 형식을 읽고 쓴다.

#### Acceptance Criteria

1. THE Restaurant_Table SHALL `note`, `collected_at`(수집일), `radius_m`(수집 반경), `anchors`(Anchor 목록과 Anchor별 Restaurant_ID 목록), `restaurants`(음식점 목록)를 포함한다
2. THE Restaurant_Table SHALL 음식점마다 `restaurant_id`, `name_ko`, `names`(영어·일본어·중국어 간체·번체 중 찾은 언어만), `lat`, `lng`, `address_ko`, `cuisine`, `kor_class`(국문 분류 코드 원본), `menu_raw`(국문 대표 메뉴 원문 또는 `null`)를 포함한다
3. THE Restaurant_Table SHALL 식단(할랄·채식·비건·글루텐 등)을 나타내는 필드를 포함하지 않는다
4. THE Restaurant_Table SHALL 같은 `restaurant_id`를 두 번 포함하지 않으며, 여러 Anchor 반경에 걸친 음식점은 한 번만 저장하고 각 Anchor 목록에서 가리킨다
5. THE Restaurant_Table SHALL 같은 입력에서 항상 같은 순서(`restaurant_id` 오름차순)로 저장된다
6. THE Restaurants_Tool SHALL Restaurant_Table을 Pydantic 모델로 검증해 읽는다
7. FOR ALL 유효한 Restaurant_Table 객체, 저장한 뒤 다시 읽은 값은 원래 객체와 같다 (왕복 속성)

### Requirement 3: 주변 음식점 조회 (`get_restaurants`)

**User Story:** As a 외국인 관광객, I want 지금 보고 있는 장소 가까운 음식점을 알고 싶다, so that 일정 중간에 식사할 곳을 고를 수 있다.

#### Acceptance Criteria

1. WHEN Restaurants_Tool이 `place_id`를 받으면, THE Restaurants_Tool SHALL 그 장소 좌표에서 `radius_m` 이내의 음식점을 가까운 순으로 돌려준다
2. THE Restaurants_Tool SHALL `radius_m`의 기본값을 500, 허용 범위를 1~1000, `limit`의 기본값을 10, 허용 범위를 1~20으로 한다
3. WHEN 거리가 같은 음식점이 있으면, THE Restaurants_Tool SHALL `restaurant_id` 오름차순으로 정렬한다
4. THE Restaurants_Tool SHALL 음식점마다 `restaurant_id`, `name_ko`, `names`, `lat`, `lng`, `address_ko`, `cuisine`, `menu_raw`, `distance_m`(직선거리, 정수), `walk_min`(Travel_Rule 도보 추정, 올림)을 돌려준다
5. THE Restaurants_Tool SHALL `{"place_id", "radius_m", "total_in_radius", "restaurants": [...], "basis": {...}}` 형식의 dict를 돌려주고, `total_in_radius`는 `limit`을 적용하기 전의 개수이다
6. THE Restaurants_Tool SHALL 응답의 `basis`에 수집일, 출처(한국관광공사 TourAPI, 공공데이터포털), 거리가 직선거리 기반 추정이라는 사실, 영업시간·휴무·메뉴·식단을 보장하지 않는다는 문장을 담는다
7. WHEN 반경 안에 음식점이 없으면, THE Restaurants_Tool SHALL `restaurants`를 빈 목록으로 돌려준다
8. IF `place_id`가 `places.json`에 없으면, THEN THE Restaurants_Tool SHALL `place_not_found` Error_Result를 돌려준다
9. IF `place_id`가 Restaurant_Table의 Anchor가 아니면, THEN THE Restaurants_Tool SHALL `restaurants_not_collected` Error_Result를 돌려준다
10. IF `radius_m` 또는 `limit`이 허용 범위 밖이면, THEN THE Restaurants_Tool SHALL `invalid_argument` Error_Result를 돌려준다
11. IF Restaurant_Table을 읽을 수 없으면, THEN THE Restaurants_Tool SHALL `data_unavailable` Error_Result를 돌려준다
12. THE Restaurants_Tool SHALL 음식점의 평점, 인기, 추천 순위, 가격을 만들어 내지 않는다

### Requirement 4: 식단·운영 정보의 한계

**User Story:** As a 식단 제한이 있는 관광객, I want 데이터에 없는 정보를 사실처럼 듣고 싶지 않다, so that 잘못된 안내로 곤란해지지 않는다.

#### Acceptance Criteria

1. THE Restaurants_Tool SHALL 할랄, 채식, 비건, 알레르기, 글루텐 여부를 판단하는 필드나 문장을 돌려주지 않는다
2. THE Restaurants_Tool SHALL 응답 `basis.diet_info`에 `"not_available"`을 담는다
3. THE Restaurants_Tool SHALL `@tool` docstring(영어)에 식단 정보가 없으므로 가게에 확인하라고 안내해야 한다고 적는다
4. THE Restaurants_Tool SHALL `menu_raw`를 국문 원문 그대로 돌려주고 번역·요약·식단 해석을 하지 않는다
5. THE Restaurants_Tool SHALL 영업시간과 휴무일을 돌려주지 않는다

### Requirement 5: 대중교통 정보 입력 (`get_transit_info`)

**User Story:** As a 외국인 관광객, I want 한 장소에서 다른 장소로 지하철로 어떻게 가는지 알고 싶다, so that 이동 계획을 세울 수 있다.

#### Acceptance Criteria

1. WHEN Transit_Tool이 `from_place_id`와 `to_place_id`를 받으면, THE Transit_Tool SHALL 두 장소의 `nearest_station`(`places.json`)을 도착·출발 역으로 쓴다
2. WHEN Transit_Tool이 `from_place_id`와 `to_station`을 받으면, THE Transit_Tool SHALL 영어 역 이름을 대소문자와 앞뒤 공백을 무시하고 Station_Table의 `station`과 맞춰 도착역으로 쓴다
3. WHERE `to_place_id`와 `to_station`이 모두 주어지면, THE Transit_Tool SHALL `to_station`을 우선하고 `to_place_id`는 검증하지 않는다
4. IF `to_place_id`와 `to_station`이 모두 없으면, THEN THE Transit_Tool SHALL `missing_argument` Error_Result를 돌려준다
5. IF `from_place_id` 또는 `to_place_id`가 `places.json`에 없으면, THEN THE Transit_Tool SHALL `place_not_found` Error_Result를 돌려준다
6. IF `to_station`이 Station_Table에 없으면, THEN THE Transit_Tool SHALL `station_not_found` Error_Result를 돌려준다
7. IF 장소의 `nearest_station`이 `null`이거나 Station_Table에 없으면, THEN THE Transit_Tool SHALL `no_station` Error_Result를 돌려주고, 메시지에 동해선·경전철 역은 데이터에 없다는 사실을 담는다
8. IF `from_place_id`와 `to_place_id`가 같으면, THEN THE Transit_Tool SHALL `same_place` Error_Result를 돌려준다

### Requirement 6: 대중교통 정보 출력과 계산

**User Story:** As a 대화 에이전트와 Guardian, I want 구조화된 이동 정보를 받고 싶다, so that 문장과 점검에 같은 값을 쓸 수 있다.

#### Acceptance Criteria

1. THE Transit_Tool SHALL `{"from": {...}, "to": {...}, "subway": {...}, "total_min", "basis": {...}}` 형식의 dict를 돌려준다
2. THE Transit_Tool SHALL `from`과 `to`에 `place_id`(`to_station`으로 받았으면 `null`), `station`(영어), `station_ko`, `lines`(Station_Table 값), `is_transfer_station`(Transfer_Station 여부)을 담는다
3. THE Transit_Tool SHALL `from.walk_to_station_min`에 출발 장소에서 출발역까지, `to.walk_from_station_min`에 도착역에서 도착 장소까지 도보 추정 분을 담고, `to_station`으로 받았으면 `to.walk_from_station_min`은 0이다
4. THE Transit_Tool SHALL 도보 분을 장소와 역의 좌표 직선거리 × 경로 계수(Travel_Rule) ÷ 도보 속도로 계산하고 올림한다
5. THE Transit_Tool SHALL `subway.minutes`를 두 역의 좌표 직선거리 × 경로 계수 ÷ 지하철 속도 + 10분으로 계산하고 올린다(`return_options.subway_minutes`와 같은 값)
6. WHEN 출발역과 도착역이 같으면, THE Transit_Tool SHALL `subway.same_station`을 `true`, `subway.minutes`를 0으로 돌려준다
7. THE Transit_Tool SHALL `total_min`을 `walk_to_station_min + subway.minutes + walk_from_station_min`으로 돌려준다
8. WHEN 출발 또는 도착 장소에서 역까지 도보 추정이 20분을 넘으면, THE Transit_Tool SHALL 해당 쪽 `warnings`에 `far_from_station`을 담는다
9. THE Transit_Tool SHALL 같은 입력에 같은 결과를 돌려주고 현재 시각을 쓰지 않는다
10. THE Transit_Tool SHALL 환승 횟수, 환승 위치, 환승 시간, 어느 호선을 타는지를 만들지 않으며 `lines`는 역에 서는 호선의 참고 값이라고 밝힌다

### Requirement 7: 대중교통 정보의 한계 표기

**User Story:** As a 관광객, I want 추정과 실제를 구분해서 듣고 싶다, so that 시간표나 실시간 정보로 오해하지 않는다.

#### Acceptance Criteria

1. THE Transit_Tool SHALL 응답 `basis`에 `kind: "rule"`, `measured: false`, 사용한 Travel_Rule 값, 이동 시간이 좌표 기반 추정이라는 문장을 담는다
2. THE Transit_Tool SHALL 응답 `basis.not_included`에 `timetable`, `real_time`, `first_last_train`, `fare`, `transfer_walk`를 담아 데이터에 없는 항목을 나열한다
3. THE Transit_Tool SHALL 실시간 버스 도착 정보와 시간표 기반 정보를 돌려주지 않는다
4. THE Transit_Tool SHALL 응답 `basis`에 동해선·경전철 역이 Station_Table에 없다는 한계를 담는다
5. THE Transit_Tool SHALL 카카오 등 경로 API를 호출하지 않고 그 결과를 저장·캐시하지 않는다
6. THE Transit_Tool SHALL `@tool` docstring(영어)에 "about N minutes"로 말하고 노선·환승을 단정하지 말라는 안내와 막차·배차 간격은 모른다는 안내를 적는다

### Requirement 8: 공통 규칙

**User Story:** As a 팀원, I want 두 도구가 기존 조회 도구와 같은 방식으로 동작하길 원한다, so that 에이전트·Guardian·프론트엔드가 같은 방식으로 쓴다.

#### Acceptance Criteria

1. THE Restaurants_Tool SHALL Strands `@tool` 함수로 `backend/app/tools/restaurants.py`에 두고, THE Transit_Tool SHALL Strands `@tool` 함수로 `backend/app/tools/transit.py`에 둔다
2. THE Restaurants_Tool SHALL 실패를 예외로 던지지 않고 Error_Result로 돌려주며, THE Transit_Tool SHALL 같은 방식으로 실패를 돌려준다
3. THE Restaurants_Tool SHALL `USE_MOCK` 값과 상관없이 Restaurant_Table만 읽고 외부 API를 호출하지 않으며, THE Transit_Tool SHALL 같은 방식으로 `app/data/`의 파일만 읽는다
4. THE Restaurants_Tool SHALL 반환하는 모든 `place_id`를 `places.json`에 있는 값으로만 채우고 새 장소 ID를 만들지 않는다
5. THE Restaurants_Tool SHALL 도구 docstring(영어)에 언제 쓰는지, 입력, 출력, 오류 코드를 자세히 적고, THE Transit_Tool SHALL 같은 항목을 적는다
6. THE Restaurants_Tool SHALL `FAKE_LLM` 값과 상관없이 동작하고, THE Transit_Tool SHALL 같은 방식으로 동작한다
7. THE Restaurants_Tool SHALL 새 의존성을 추가하지 않으며, THE Transit_Tool SHALL 같은 방식으로 추가하지 않는다
8. THE info-tools 작업 SHALL 공용 파일(`backend/app/models/`, `docs/api-contract.md`, `backend/app/handler.py`, `.kiro/steering/team.md`)과 `agent.py`, `chat/`을 수정하지 않고 필요한 수정안만 `design.md`에 적는다
9. THE info-tools 작업 SHALL 테스트를 `backend/tests/test_restaurants.py`와 `backend/tests/test_transit.py`에 두고, 외부 API 없이 `USE_MOCK=1`, `FAKE_LLM=1`에서 통과하게 한다
