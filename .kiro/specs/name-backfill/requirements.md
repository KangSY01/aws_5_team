# Requirements Document

## Introduction

`backend/app/data/places.json`의 장소 33곳 중 일부는 외국어 이름(en, ja, zh-Hans, zh-Hant)이 비어 있다. 데모 손님이 일본인 커플이므로 ja가 가장 급하다. ja가 없는 곳은 the-bay-101, busan-x-the-sky, sea-life-busan, busan-cinema-center, lotte-world-busan, lotte-outlet-dongbusan, songdo-cable-car, busan-citizens-park, busan-museum 9곳이며, 해운대 3곳(the-bay-101, busan-x-the-sky, sea-life-busan)을 먼저 확인한다. 다른 언어의 빈칸은 `places_review.csv`에 있다.

기존 방식(`fetch_places.py`)은 외국어 서비스의 `locationBasedList2`를 국문 좌표 반경으로 조회한다. 이 API는 항목을 빠뜨린다(`fetch_restaurants.py`에서 확인). 이 기능은 외국어 4개 서비스(EngService2, JpnService2, ChsService2, ChtService2)의 부산 전체 `areaBasedList2`를 언어별로 받아 raw에 저장하고, 빠진 언어만 기존 일치 규칙(`pick_foreign`: 괄호 안 한국어 일치 + 거리)으로 채운다. 기존 이름은 덮어쓰지 않고, 지어내지 않으며, 못 찾으면 review에 남긴다.

작업 범위는 `backend/app/data/`와 `backend/scripts/`이다. 공용 파일(`backend/app/models/`, `docs/api-contract.md`, `backend/app/handler.py`, `.kiro/steering/team.md`)은 수정하지 않는다. commit과 push는 하지 않는다.

## Glossary

- **Backfill_Script**: 부산 전체 목록을 받아 빠진 외국어 이름을 채우는 스크립트 (`backend/scripts/` 아래, 이름은 설계에서 정한다)
- **Places_File**: `backend/app/data/places.json`
- **Sources_File**: `backend/app/data/places_sources.json`
- **Review_File**: `backend/app/data/places_review.csv`
- **Raw_Store**: `backend/app/data/raw/` (API 원본 응답, git에 올리지 않음, serviceKey 미저장)
- **Foreign_Service**: 외국어 TourAPI 4개 서비스(EngService2, JpnService2, ChsService2, ChtService2)
- **Area_List**: Foreign_Service의 `areaBasedList2` 응답 중 `lDongRegnCd=26`(부산 전체)을 관광 관련 타입별로 받은 목록
- **Target_Types**: 관광지·문화시설·쇼핑 등 장소 이름이 들어 있는 외국어 관광타입 집합. 번호는 실제 응답으로 확인해 정한다(국문과 번호 체계가 다르다).
- **Match_Rule**: `fetch_places.pick_foreign`의 일치 규칙. 한글·숫자 정규화 값이 같으면 exact, 300m 이내에서 짧은 쪽이 3글자 이상 포함되면 contains. exact가 contains보다 우선하고 같은 종류끼리는 가까운 쪽을 고른다.
- **Missing_Language**: Places_File의 장소 `names`에 없는 언어 (en, ja, zh-Hans, zh-Hant 중)
- **Haeundae_Three**: the-bay-101, busan-x-the-sky, sea-life-busan
- **Linked_Scripts**: `build_travel_times`, `build_curation`, `build_congestion`, `build_stations` 4개 스크립트
- **API_Call_Count**: 한 번의 실행에서 실제로 보낸 HTTP 요청 수 (재시도 포함, `fetch_places.API_CALLS`와 같은 기준)
- **Baseline_IDs**: 실행 시작 시점에 Places_File에 있던 `place_id` 집합. 새 장소 판단의 기준이다.
- **Fill_Report**: 언어별 채움 수 전후 비교, Haeundae_Three의 ja 결과, biff-square·jeonpo-cafe-street 결과, API_Call_Count를 담은 결과 보고

## Requirements

### Requirement 1: 부산 전체 외국어 목록 수집

**User Story:** 데이터 담당자로서, 외국어 4개 서비스의 부산 전체 목록을 언어별로 받아 두고 싶다. 좌표 조회가 빠뜨리는 항목까지 후보로 쓰기 위해서다.

#### Acceptance Criteria

1. WHEN Backfill_Script가 수집 모드로 실행되면, THE Backfill_Script SHALL Foreign_Service 4개 각각에 `areaBasedList2`를 `lDongRegnCd=26`과 Target_Types의 각 `contentTypeId`로 호출하고, 응답의 `totalCount`만큼 건수를 받을 때까지 쪽 번호를 1부터 1씩 올려 모든 쪽을 받는다.
2. WHEN Backfill_Script가 응답을 받으면, THE Backfill_Script SHALL 그 응답 원본을 serviceKey 값 없이 Raw_Store에 언어별·타입별·쪽별로 파일 하나씩 따로 저장한다.
3. THE Backfill_Script SHALL 모든 외부 API 호출에 타임아웃 5초와 재시도 최대 1회를 적용한다.
4. IF 호출이 타임아웃되거나 오류 응답을 받고 재시도 1회도 같은 결과로 끝나면, THEN THE Backfill_Script SHALL 그 호출을 실패로 처리하고 이미 저장한 Raw_Store 파일을 그대로 유지한다.
5. WHILE Raw_Store에 같은 요청(서비스, 작업, 파라미터)의 응답이 있으면, THE Backfill_Script SHALL 그 요청을 다시 호출하지 않고 저장된 응답을 읽는다.
6. IF 한 언어의 호출이 실패하면, THEN THE Backfill_Script SHALL 그 언어를 `api_error: <사유>` 형식으로 Review_File에 기록하고, 나머지 언어의 처리를 계속하며, 실행 종료 시 실패한 언어 수를 출력한다.
7. IF 응답의 `totalCount`가 받은 건수보다 크면, THEN THE Backfill_Script SHALL 해당 언어·타입의 `totalCount`와 받은 건수를 함께 담은 경고를 출력한다.
8. WHEN Backfill_Script가 수집 모드로 실행되면, THE Backfill_Script SHALL 목록 호출 전에 Target_Types의 번호를 실제 응답(타입 없이 받은 목록 1회 또는 응답의 `contenttypeid` 값)으로 확인하고, 확인 근거(사용한 응답과 번호별 확인 결과)를 Fill_Report에 기록한다.
9. IF Target_Types의 번호가 실제 응답의 `contenttypeid` 값과 일치하지 않으면, THEN THE Backfill_Script SHALL 목록 호출을 시작하지 않고, 불일치한 번호를 Fill_Report에 기록하며, 오류를 출력하고 종료한다.

### Requirement 2: 빠진 언어만 채우기

**User Story:** 데이터 담당자로서, 비어 있는 언어 이름만 기존 규칙으로 채우고 싶다. 이미 검증된 이름이 바뀌지 않게 하기 위해서다.

#### Acceptance Criteria

1. WHEN Area_List가 준비되면, THE Backfill_Script SHALL Places_File의 장소마다 `names`에서 값이 비어 있는 언어(Missing_Language)에 대해서만 Match_Rule로 일치 항목을 찾는다.
2. WHEN 일치 항목이 있으면, THE Backfill_Script SHALL 외국어 title에서 한국어 문자를 모두 제거한 값(`strip_korean`)을 그 장소·언어의 이름으로 사용한다.
3. IF `strip_korean` 결과가 공백만 남거나 빈 문자열이면, THEN THE Backfill_Script SHALL 해당 이름을 비워 두고 Review_File에 사유 `empty_name`(기존 `fetch_places`와 같은 사유 이름)과 후보를 기록한다.
4. WHEN 일치 항목이 있고 `strip_korean` 결과가 1자 이상이면, THE Backfill_Script SHALL 그 이름을 해당 장소의 `names`에 넣고 Sources_File에 `contentids`, `apis`, `match_kind`를 기록한다.
5. THE Backfill_Script SHALL Places_File에서 값이 이미 있는 이름을 실행 전과 한 글자도 다르지 않게 유지한다.
6. THE Backfill_Script SHALL 장소의 `place_id`, 좌표, `category`, `indoor`, `nearest_station`을 실행 전과 같은 값으로 유지한다.
7. IF Match_Rule로 일치 항목을 찾지 못하면, THEN THE Backfill_Script SHALL 이름을 비워 두고 Review_File에 사유 `no_korean_match`와 후보 목록(없으면 빈 목록)을 기록한다.
8. IF 일치 항목은 있으나 Foreign_Service 응답의 title 필드가 없거나 빈 문자열이면, THEN THE Backfill_Script SHALL 이름을 비워 두고 Review_File에 사유 `empty_name`(2.3과 같은 사유)과 후보를 기록한다.
9. THE Backfill_Script SHALL 이름으로 Foreign_Service 응답의 title에서 `strip_korean`으로 얻은 값만 사용하고, 번역하거나 새로 만든 문자열을 `names`에 넣지 않는다.
10. IF 같은 일치 종류(`match_kind`)의 후보가 둘 이상이고 `strip_korean` 이름이 서로 다르면, THEN THE Backfill_Script SHALL 장소 좌표와의 거리가 가장 가까운 후보를 선택하고 해당 장소·언어를 후보 목록, 선택한 후보와 함께 Review_File에 기록한다.
11. IF 거리가 같은 후보가 둘 이상이면, THEN THE Backfill_Script SHALL `contentid`가 가장 작은 후보를 선택하고 Review_File에 기록한다.
12. WHEN 채우기가 끝나면, THE Backfill_Script SHALL Places_File의 모든 장소를 `Place` 모델로 검증하고, 하나라도 실패하면 Places_File을 쓰지 않고 실패한 `place_id`를 출력하며 실패로 종료한다.

### Requirement 3: 일치 규칙 재사용

**User Story:** 데이터 담당자로서, 새 스크립트가 기존 규칙과 같은 기준으로 일치 여부를 판단하길 원한다. 두 경로의 결과가 어긋나지 않게 하기 위해서다.

#### Acceptance Criteria

1. THE Backfill_Script SHALL `fetch_places`의 `pick_foreign`, `normalize_korean`, `strip_korean`, `haversine_m`을 import해서 사용하고, 같은 일치 규칙을 별도 함수로 다시 구현하지 않는다.
2. WHEN 같은 국문 기준 응답과 같은 외국어 후보 목록을 입력하면, THE Backfill_Script SHALL `fetch_places`가 선택하는 후보와 동일한 후보를 선택한다.
3. THE Backfill_Script SHALL `fetch_places.py`, `fetch_restaurants.py`의 동작과 출력 파일 형식을 바꾸지 않는다. 두 파일은 이 작업 전후로 내용이 동일하다.
4. THE Backfill_Script SHALL 국문 기준 title과 좌표를 `app/data/raw/<place_id>/ko.json`에 저장된 국문 응답에서 읽고, 국문 API를 호출하지 않는다.
5. IF `app/data/raw/<place_id>/ko.json`이 없거나, 파일을 JSON으로 읽을 수 없거나, title 또는 좌표 값이 없으면, THEN THE Backfill_Script SHALL 그 장소를 건너뛰고, Review_File에 사유 `kor_raw_missing`과 해당 `place_id`를 기록하고, 나머지 장소의 처리를 계속한다.
6. IF 한 장소를 건너뛰면, THEN THE Backfill_Script SHALL 그 장소의 기존 Raw_Store 파일과 `places.json` 항목을 수정하지 않는다.

### Requirement 4: 기존 값 보호와 출처 기록

**User Story:** 데이터 담당자로서, 이번 작업이 이전에 수집한 값과 출처 기록을 훼손하지 않기를 원한다. 이름의 출처를 계속 추적하기 위해서다.

#### Acceptance Criteria

1. WHEN Backfill_Script가 Sources_File을 갱신할 때, THE Backfill_Script SHALL 이번에 채운 장소·언어 조합의 항목만 추가하거나 갱신하고, 그 외 모든 언어 항목의 `contentids`, `apis`, `match_kind`, `match_radius_m` 값을 실행 전과 동일하게 유지한다.
2. WHEN Backfill_Script가 장소·언어 조합의 이름을 채울 때, THE Backfill_Script SHALL 해당 Sources_File 항목의 `apis`에 `areaBasedList2`를 포함시켜 다른 API로 찾은 항목과 구분할 수 있게 한다.
3. WHEN Backfill_Script가 Review_File을 갱신할 때, THE Backfill_Script SHALL 이번에 채운 장소·언어의 행만 삭제하고, 채우지 못한 장소·언어의 행은 내용 변경 없이 유지한다.
4. WHEN Backfill_Script가 Review_File을 갱신할 때, THE Backfill_Script SHALL `kept_existing` 등 이번 작업 대상이 아닌 행을 내용과 순서 변경 없이 유지한다.
5. WHEN Backfill_Script가 Places_File과 Sources_File을 쓸 때, THE Backfill_Script SHALL 두 파일을 BOM 없는 UTF-8로 저장한다.
6. WHEN Backfill_Script가 Review_File을 쓸 때, THE Backfill_Script SHALL 엑셀 호환을 위해 기존과 같이 BOM이 있는 UTF-8(`utf-8-sig`)로 저장한다. 이 인코딩은 5번의 BOM 없는 UTF-8 규칙에서 Review_File만 제외한 예외이다.
7. WHEN Backfill_Script가 Places_File을 쓸 때, THE Backfill_Script SHALL 기존 `dump_places` 형식으로 저장하며, 각 장소의 `names` 객체를 한 줄로 쓴다.
8. IF Backfill_Script가 Places_File, Sources_File, Review_File 중 하나를 쓰는 도중 오류가 발생하면, THEN THE Backfill_Script SHALL 오류 원인을 나타내는 한국어 로그를 남기고 0이 아닌 종료 코드로 끝나며, 쓰기 전에 저장된 세 파일의 기존 내용을 손상시키지 않는다.

### Requirement 5: biff-square 재시도

**User Story:** 데이터 담당자로서, 국문 검색이 0건이었던 biff-square를 띄어쓰기를 바꿔 다시 찾고 싶다. 장소를 복원하기 위해서다.

#### Acceptance Criteria

1. WHEN 시드를 갱신하면, THE Backfill_Script SHALL `backend/scripts/place_seeds.json`의 biff-square 항목 `query`를 "BIFF광장"에서 "BIFF 광장"(띄어쓰기)으로 바꿔 저장하고, 바꾼 `query`로 `searchKeyword2`를 정확히 1회 호출한다. 시드 파일의 이 값 변경은 이 작업에 포함된다. 호출 실패 시 재시도는 1회까지 허용하며, 외부 API 타임아웃은 5초로 한다.
2. WHEN `searchKeyword2` 결과가 반환되고 주소가 "부산"으로 시작하는 후보가 정확히 1건이거나 제목이 시드 이름과 정확히 같은 후보가 정확히 1건이면, THE Backfill_Script SHALL 그 후보로 국문 좌표를 정하고 장소를 Places_File에 추가한다.
3. IF 결과가 0건이거나 위 2번 조건을 만족하는 후보가 0건 또는 2건 이상이어서 후보를 하나로 정할 수 없으면, THEN THE Backfill_Script SHALL 장소를 Places_File에 추가하지 않고, 사유(0건 또는 후보 다수)와 후보 목록(제목, 주소, 좌표)을 Review_File에 기록한다. 이때 Places_File의 기존 내용은 변경하지 않는다.
4. IF 재시도 후에도 `searchKeyword2` 호출이 실패하거나 타임아웃되면, THEN THE Backfill_Script SHALL 장소를 Places_File에 추가하지 않고, 호출 실패 사유를 Review_File에 기록하며, 비정상 종료를 알리는 오류를 출력한다. 이때 Places_File의 기존 내용은 변경하지 않는다.
5. THE Backfill_Script SHALL 추가한 장소의 `place_id`를 시드에 있는 `biff-square`로 쓰고 새 ID를 만들지 않는다.
6. WHEN 장소를 추가하기로 정하면, THE Backfill_Script SHALL Match_Rule과 Area_List로 그 장소의 빠진 언어(영어, 일본어, 중국어 간체, 중국어 번체 중 채워지지 않은 언어)를 채운다.
7. IF 국문 좌표가 없거나 외국어 이름이 0개이면, THEN THE Backfill_Script SHALL 그 장소를 Places_File에 넣지 않고 사유를 Review_File에 기록한다. 좌표가 있고 외국어 이름이 1개 이상일 때만 Places_File에 넣는다.

### Requirement 6: jeonpo-cafe-street 복원

**User Story:** 데이터 담당자로서, 외국어 이름이 없어 제외된 jeonpo-cafe-street를 목록에서 이름이 나오면 복원하고 싶다. 근거 없이 추가하지 않기 위해서다.

#### Acceptance Criteria

1. WHEN Area_List에서 jeonpo-cafe-street의 국문 좌표와 Match_Rule로 일치하는 외국어 항목이 1개 이상 나오면, THE Backfill_Script SHALL 일치한 항목의 이름을 언어별로 그대로 사용해 jeonpo-cafe-street를 Places_File에 1건 복원한다.
2. IF 일치하는 외국어 항목이 2개 이상이고 같은 언어에 서로 다른 이름이 있으면, THEN THE Backfill_Script SHALL Match_Rule의 거리 기준에서 국문 좌표와 가장 가까운 항목의 이름을 쓰고, 나머지 항목을 후보로 Review_File에 남긴다.
3. IF 일치하는 외국어 항목이 없으면, THEN THE Backfill_Script SHALL Places_File에 jeonpo-cafe-street를 추가하지 않고, 사유 "일치 항목 없음"과 조회한 후보 목록(0건이면 빈 목록)을 Review_File에 남긴다.
4. IF jeonpo-cafe-street의 시드, 국문 좌표 또는 raw 중 하나라도 현재 없으면, THEN THE Backfill_Script SHALL 없는 항목의 종류를 Fill_Report에 적고, 이를 채우려고 추가한 시드 항목 수와 국문 조회 호출 수 1회를 API_Call_Count에 포함한다.
5. THE Backfill_Script SHALL 복원하는 장소의 `category`와 `indoor`를 시드에 적힌 값으로 쓴다. WHEN jeonpo-cafe-street 시드가 `place_seeds.json`에 없어 이 작업에서 새로 추가하면, THE Backfill_Script SHALL 그 시드의 `category`를 "street", `indoor`를 false로 적는다.
6. IF 시드에 `category` 또는 `indoor` 값이 없으면, THEN THE Backfill_Script SHALL Places_File에 jeonpo-cafe-street를 추가하지 않고, 사유 `missing_category_or_indoor`를 Review_File에 남긴다.
7. IF Backfill_Script가 jeonpo-cafe-street를 복원하지 않으면, THEN THE Backfill_Script SHALL Places_File의 기존 장소 항목을 변경하지 않고 그대로 둔다.

### Requirement 7: 연결 스크립트 재실행

**User Story:** 데이터 담당자로서, 장소가 새로 들어오면 파생 파일이 함께 갱신되길 원한다. `get_place_info`와 이동·혼잡 도구가 새 장소를 알게 하기 위해서다.

#### Acceptance Criteria

1. WHEN Places_File의 `place_id` 집합에 Baseline_IDs에 없던 값이 하나 이상 생기면, THE Backfill_Script SHALL `build_travel_times`, `build_curation`, `build_congestion`, `build_stations`를 이 순서로 각각 1회 실행한다.
2. IF 앞 단계 스크립트가 0이 아닌 종료 코드로 끝나면, THEN THE Backfill_Script SHALL 남은 단계를 실행하지 않고, 실패한 단계 이름을 Fill_Report에 적고, 0이 아닌 종료 코드로 끝나며, 이미 생성된 파생 파일은 변경하지 않고 둔다.
3. WHEN Places_File에 새 `place_id`가 없고 하나 이상의 장소에서 `names`의 빈 언어가 채워졌으면, THE Backfill_Script SHALL `build_curation`만 다시 실행한다(`foreigner_friendly`가 이름 수에서 나오기 때문이다).
4. WHERE 새 `place_id`가 `build_congestion.PLACE_NAMES`에 없으면, THE Backfill_Script SHALL 해당 장소의 혼잡도 연결 표를 생성하지 않고, 그 장소를 "요일 규칙 대체 대상"으로 Fill_Report에 `place_id`와 함께 적는다.
5. IF 새 장소의 `nearest_station` 값이 `stations.json`에 없으면, THEN THE Backfill_Script SHALL 해당 `place_id`와 `nearest_station` 값을 담은 경고를 Fill_Report에 적고 나머지 단계는 계속 실행한다.
6. THE Backfill_Script SHALL 실행 전에 `curation_overrides.json`에 있던 모든 수동 항목을 실행 후에도 같은 값으로 유지한다.

### Requirement 8: 호출 수 제한

**User Story:** 데이터 담당자로서, API 호출을 꼭 필요한 만큼만 쓰고 싶다. 일일 호출 한도를 아끼기 위해서다.

#### Acceptance Criteria

1. WHEN Backfill_Script가 전체 실행(실제 API 호출)을 수행하면, THE Backfill_Script SHALL 외국어 4개 서비스 각각에 대해 Target_Types 수 × 쪽 수만큼만 API를 호출하고, 같은 서비스·작업·쪽 조합에 대한 확인용 반복 호출을 0회로 유지한다.
2. WHERE `--offline` 옵션이 지정되면, THE Backfill_Script SHALL API 호출 횟수 0회로 Raw_Store에 저장된 응답만 사용한다.
3. IF `--offline` 옵션에서 필요한 응답이 Raw_Store에 없으면, THEN THE Backfill_Script SHALL API를 호출하지 않고, 누락된 서비스·작업·쪽을 알리는 오류를 출력한 뒤 0이 아닌 종료 코드로 종료하며, Raw_Store의 기존 응답은 변경하지 않는다.
4. WHEN 테스트를 실행하면, THE 테스트 SHALL 외부 API 호출 0회로 합성 응답과 Raw_Store에 저장된 응답만 사용한다.
5. WHEN 테스트가 모두 통과하면, THE 작업자 SHALL 전체 실행(실제 API 호출)을 정확히 1회만 수행한다.
6. WHEN 실행이 종료되면(성공·실패 모두), THE Backfill_Script SHALL API_Call_Count를 서비스별·작업별로 출력한다.
7. IF 실행이 실패해 다시 실행해야 하면, THEN THE 작업자 SHALL `--reuse-raw`를 지정해 Raw_Store에 이미 저장된 서비스·작업·쪽의 응답에는 API를 다시 호출하지 않고(재호출 0회), 저장되지 않은 서비스·작업·쪽에만 호출한다.

### Requirement 9: 결과 보고

**User Story:** 팀원으로서, 무엇이 얼마나 채워졌는지 한눈에 보고 싶다. 데모 전에 남은 빈칸을 판단하기 위해서다.

#### Acceptance Criteria

1. WHEN 작업이 끝나면, THE Fill_Report SHALL en, ja, zh-Hans, zh-Hant 각 언어별로 이름이 있는 장소 수를 "작업 전 N곳 / 작업 후 M곳 / 증감 (M−N)" 세 값으로 한 표에 나란히 보여 준다.
2. WHEN 작업이 끝나면, THE Fill_Report SHALL Haeundae_Three 각각(장소 ID 기준 항목 1개씩)에 대해 ja 결과를 보여 준다. 이름을 채운 경우에는 채운 이름, 일치 종류, 거리(미터 단위)를 보여 주고, 못 채운 경우에는 사유를 보여 준다.
3. WHEN 작업이 끝나면, THE Fill_Report SHALL biff-square와 jeonpo-cafe-street 각각에 대해 Places_File 추가 여부(추가됨/추가 안 됨), 추가한 경우 이름, 추가하지 않은 경우 사유를 보여 준다.
4. WHEN 작업이 끝나면, THE Fill_Report SHALL 작업 후에도 이름이 비어 있는 모든 (장소 ID, 언어) 쌍을 빠짐없이 나열하고, Review_File에 남은 항목 수를 사유별로 보여 준다. 비어 있는 쌍이 없으면 "없음"으로 표시한다.
5. WHEN 작업이 끝나면, THE Fill_Report SHALL API_Call_Count를 정수로, Linked_Scripts 재실행 여부를 스크립트별 "실행함/실행 안 함"으로 보여 준다.
6. THE Fill_Report SHALL 작업 전 수치를 Places_File을 처음 수정하기 전에 측정해 기록한다.
7. IF 작업 전 수치가 Places_File 수정 전에 측정되지 않았거나 측정에 실패했다면, THEN THE Fill_Report SHALL 해당 수치를 "측정 안 됨"으로 표시하고 작업 후 수치만 보여 준다. 이때 추정값으로 작업 전 수치를 채우지 않는다.

### Requirement 10: 테스트 가능한 순수 로직과 형식 검증

**User Story:** 개발자로서, 채우기 규칙이 입력에 따라 올바르게 동작하는지 자동으로 확인하고 싶다. API 없이 회귀를 막기 위해서다.

#### Acceptance Criteria

1. THE Backfill_Script SHALL 후보 목록과 기존 `names`를 입력받아 새 `names`와 review 행 목록을 반환하는 순수 함수를 제공하며, 이 함수는 네트워크 호출, 파일 읽기·쓰기, 환경 변수 읽기, 현재 시각 읽기를 하지 않는다.
2. FOR ALL 기존 `names`와 후보 목록에 대해, THE 순수 함수 SHALL 기존 `names`의 모든 키와 값을 결과 `names`에 변경 없이 보존한다 (불변 속성). 결과 `names`의 키 집합은 기존 키 집합을 포함해야 한다.
3. FOR ALL 입력에 대해, THE 순수 함수 SHALL 첫 번째 적용 결과의 `names`를 기존 `names`로 삼아 같은 후보 목록으로 다시 적용했을 때 `names`가 첫 번째 결과와 동일하고, 추가되는 review 행이 0건이 되게 한다 (멱등 속성).
4. FOR ALL 입력에 대해, THE 순수 함수 SHALL 기존 `names`에 없던 키에 새로 채운 모든 이름이 후보 title에 `strip_korean`을 적용해 얻은 값 중 하나와 정확히 일치하게 한다 (지어내지 않는 속성). 후보 목록이 비어 있으면 새로 채운 이름은 0건이다.
5. WHEN API 응답의 `items`가 빈 문자열이거나, `item`이 목록이 아닌 단일 dict이거나, 후보가 0건이면, THE Backfill_Script SHALL 예외를 발생시키지 않고 처리한다. 이때 단일 dict는 후보 1건으로, 빈 문자열과 0건은 후보 0건으로 취급하며, 후보 0건이면 기존 `names`를 변경하지 않고 반환한다.
6. WHEN 테스트가 임시 디렉터리에 Places_File과 Sources_File을 저장한 뒤 다시 읽으면, THE 테스트 SHALL 다시 읽은 객체가 저장 전 객체와 모든 키와 값에서 동일한지(한글·일본어·중국어 문자 포함) 확인한다 (왕복 속성). THE 테스트 SHALL 실제 `backend/app/data/` 원본 파일을 수정하지 않는다.
7. THE 테스트 SHALL `backend/tests/test_name_backfill.py`에 위치하며, 외부 API 호출과 API 키 없이 `uv run pytest backend/tests/test_name_backfill.py`로 실행되어 통과해야 한다.
8. WHERE 속성 기반 테스트를 쓰는 경우, THE 테스트 SHALL 불변·멱등·지어내지 않는 속성을 각각 최소 100개의 서로 다른 입력으로 검증한다.
9. IF 순수 함수가 `item` 필드 누락, `title` 값이 None 또는 빈 문자열인 후보를 받으면, THEN THE 순수 함수 SHALL 해당 후보를 건너뛰고 나머지 후보를 계속 처리하며, 건너뛴 후보로 `names`를 변경하지 않는다.