# Implementation Plan: name-backfill (구현 계획)

## Overview

`backend/scripts/backfill_names.py` 하나에 순수 함수 구역과 입출력 구역을 만들고, `backend/tests/test_name_backfill.py`에 테스트를 쓴다. 구현 언어는 Python(설계 문서가 Python 코드를 쓴다)이다.

진행 순서는 다음과 같다.

1. 순수 함수를 먼저 만들고 속성 테스트로 검증한다.
2. 입출력 구역(수집, 복원, 파일 쓰기, 보고)을 가짜 객체와 `tmp_path`로 검증한다.
3. `main`으로 전체를 연결한다.
4. 테스트가 모두 통과한 뒤에만 마지막 쪽에서 실제 API 전체 실행을 1회 한다.

## 공통 제약

- 속성 검증은 `hypothesis` 없이 `pytest.mark.parametrize` 일반 테스트로 한다. 입력은 손으로 고른 경계 케이스와 `random.Random(고정 시드)` 난수 입력을 합쳐 속성마다 100개 이상(중복 제거 후)으로 한다. `backend/pyproject.toml`과 `backend/uv.lock`은 수정하지 않는다.
- 작업 6(체크포인트)을 통과하기 전에는 실제 API를 한 번도 호출하지 않는다. 모든 테스트는 가짜 `request_json`, 합성 응답, `tmp_path`만 쓰고 실제 `backend/app/data/` 파일을 바꾸지 않는다.
- 공용 파일(`backend/app/models/`, `docs/api-contract.md`, `backend/app/handler.py`, `.kiro/steering/team.md`)과 `fetch_places.py`, `fetch_restaurants.py`는 수정하지 않는다.
- commit과 push는 하지 않는다.
- 주석과 로그는 한국어로 쓴다. 로그, 보고서, raw에 `serviceKey` 값을 쓰지 않는다.
- 새 장소 ID는 만들지 않는다. 시드에 있는 `biff-square`, `jeonpo-cafe-street`만 쓴다.

## Tasks

- [x] 1. 순수 함수 구역 구현
  - [x] 1.1 스크립트 뼈대와 보조 순수 함수 작성
    - `backend/scripts/backfill_names.py`를 만들고 `fetch_places`에서 `pick_foreign`, `normalize_korean`, `strip_korean`, `haversine_m`, `match_kind`를 import한다. 같은 이름의 함수는 정의하지 않는다.
    - 상수 `REGION_CODE`, `AREA_ROWS`, `MAX_PAGES`, `EXPECTED_CALLS=30`, `MAX_CALLS=45`, `SEEDS_PATH`, `TARGET_TYPES`, `NAME_LANGS`, `RAW_DIR`, `RESTORE_SEEDS`를 정의한다.
    - `FilledName`, `FillResult` 데이터클래스를 정의한다.
    - `missing_langs`, `sanitize_candidates`, `plan_pages`, `check_budget`, `count_names`, `remaining_gaps`를 구현한다.
    - _Requirements: 1.1, 2.1, 3.1, 8.1, 9.1, 9.4, 10.1, 10.9_

  - [x] 1.2 `fill_names`와 `apply_fill` 구현
    - 빠진 언어만 대상으로 하고, 후보를 `contentid` 오름차순으로 정렬한 뒤 `fp.pick_foreign`을 반경 300m, 없으면 1000m 순서로 부른다.
    - `strip_korean` 결과만 이름으로 쓰고, 선택 불가·동률·모호 사유(`no_korean_match`, `empty_name`, `ambiguous_match`, `distance_tie`)를 review 행으로 만든다. `known_reviews`에 있는 쌍에는 행을 만들지 않는다.
    - 후보 키가 없는 언어(수집 실패)는 건드리지 않는다.
    - `apply_fill`은 `names` 외 필드를 그대로 둔다.
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 3.2, 10.1, 10.2, 10.3, 10.4, 10.5, 10.9_

  - [x]* 1.3 속성 테스트: 채우기는 기존 값을 바꾸지 않는다
    - `backend/tests/test_name_backfill.py`에 작성한다. 태그 주석 `# Feature: name-backfill, Property 1`.
    - 경계 케이스와 고정 시드 난수를 합쳐 `parametrize` 입력 100개 이상, 길이 확인 테스트 포함.
    - **Property 1: 채우기는 기존 값을 바꾸지 않는다**
    - **Validates: Requirements 2.5, 2.6, 10.2**

  - [x]* 1.4 속성 테스트: 같은 입력으로 다시 적용해도 결과가 같다
    - 첫 결과의 `names`와 review 쌍을 `known_reviews`로 넘겨 재적용한다.
    - **Property 2: 같은 입력으로 다시 적용해도 결과가 같다**
    - **Validates: Requirements 10.3**

  - [ ]* 1.5 속성 테스트: 이름은 후보 title의 strip_korean 값뿐이다
    - **Property 3: 이름은 후보 title의 strip_korean 값뿐이다**
    - **Validates: Requirements 2.2, 2.9, 10.4**

  - [ ]* 1.6 속성 테스트: 쓸 수 없는 후보는 없는 것과 같다
    - 불량 후보(None·빈·공백 title, 필드 누락, dict 아님)와 `items` 형태(빈 문자열, 단일 dict, 목록, 0건)를 포함한다.
    - **Property 4: 쓸 수 없는 후보는 없는 것과 같다**
    - **Validates: Requirements 10.5, 10.9**

  - [ ]* 1.7 속성 테스트: 후보 선택이 기존 일치 규칙과 같다
    - `fp.pick_foreign`을 오라클로 쓴다.
    - **Property 5: 후보 선택이 기존 일치 규칙과 같다**
    - **Validates: Requirements 2.1, 3.2**

  - [ ]* 1.8 속성 테스트: 같은 종류 후보가 여럿이면 가장 가까운 것, 거리까지 같으면 contentid가 작은 것
    - 입력 순서를 섞어 검증한다.
    - **Property 6: 같은 종류 후보가 여럿이면 가장 가까운 것, 거리까지 같으면 contentid가 작은 것**
    - **Validates: Requirements 2.10, 2.11, 6.2**

  - [ ]* 1.9 속성 테스트: 못 채운 언어는 사유가 있는 review 행이 정확히 한 건이다
    - 수집 실패 언어는 이름도 행도 바뀌지 않음을 함께 확인한다.
    - **Property 7: 못 채운 언어는 사유가 있는 review 행이 정확히 한 건이다**
    - **Validates: Requirements 2.3, 2.7, 2.8**

  - [ ]* 1.10 속성 테스트: 쪽 계획은 totalCount만큼의 건수를 모두 덮는다
    - **Property 11: 쪽 계획은 totalCount만큼의 건수를 모두 덮는다**
    - **Validates: Requirements 1.1, 1.7, 8.1**

  - [ ]* 1.11 속성 테스트: 보고 수치는 실제 변화와 맞는다
    - `count_names` 증감과 `remaining_gaps`를 확인한다.
    - **Property 14: 보고 수치는 실제 변화와 맞는다**
    - **Validates: Requirements 9.1, 9.4**

  - [ ]* 1.12 `check_budget` 경계값 단위 테스트
    - `used + 2 > max`, `used + pending > max`, 정상 진행 경계를 `parametrize`로 확인한다.
    - _Requirements: 8.1_

- [x] 2. 병합, 직렬화, 연결 계획 구현
  - [x] 2.1 병합과 직렬화 순수 함수 구현
    - `merge_sources`(채운 쌍만 갱신, `apis`에 `areaBasedList2` 포함, `contentids`·`match_kind`·`match_radius_m` 기록), `merge_review`(채운 쌍의 행만 삭제, `kept_existing` 등 순서 유지, 새 행은 뒤에 추가, 성공한 언어의 `api_error` 행 삭제), `dump_sources`, `dump_review`(`utf-8-sig`, CRLF), `dump_places`(`fp.dump_places` 결과를 CRLF로)를 구현한다.
    - _Requirements: 2.4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 2.2 속성 테스트: 파일 직렬화는 왕복해도 같고 형식을 지킨다
    - 한글·일본어·중국어 문자, BOM 없음(review는 `utf-8-sig`), `names` 한 줄, 다시 읽은 객체 동일을 확인한다.
    - **Property 8: 파일 직렬화는 왕복해도 같고 형식을 지킨다**
    - **Validates: Requirements 4.5, 4.7, 10.6**

  - [ ]* 2.3 속성 테스트: review 병합은 채운 쌍의 행만 지운다
    - **Property 9: review 병합은 채운 쌍의 행만 지운다**
    - **Validates: Requirements 4.3, 4.4**

  - [ ]* 2.4 속성 테스트: sources 병합은 채운 쌍의 항목만 바꾼다
    - **Property 10: sources 병합은 채운 쌍의 항목만 바꾼다**
    - **Validates: Requirements 2.4, 4.1, 4.2**

  - [x] 2.5 `plan_linked_steps`와 `run_chain` 구현
    - 새 `place_id`가 있으면 `build_travel_times` → `build_curation` → `build_congestion` → `build_stations`, 새 ID 없이 채운 이름이 있으면 `build_curation` 하나, 둘 다 없으면 빈 목록을 돌려준다.
    - `run_chain`은 첫 실패에서 멈추고 (실행한 목록, 실패한 이름)을 돌려준다. 예외도 실패로 처리한다.
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ]* 2.6 속성 테스트: 연결 스크립트는 정해진 순서로 실행되고 첫 실패에서 멈춘다
    - **Property 13: 연결 스크립트는 정해진 순서로 실행되고 첫 실패에서 멈춘다**
    - **Validates: Requirements 7.1, 7.2, 7.3**

- [ ] 3. Checkpoint - 순수 함수 구역 점검
  - `backend/`에서 `uv run pytest tests/test_name_backfill.py`가 통과하는지 확인한다. 실제 API는 호출하지 않는다. 문제가 있으면 사용자에게 묻는다.

- [x] 4. 입출력 구역 구현
  - [x] 4.1 수집 함수와 호출 수 관리 구현
    - `CallLog`(`fp.API_CALLS` 증가량을 (서비스, 작업)별 합산), `CallBudget`(`check_budget` 호출, 초과 시 `BudgetExceeded`)을 만든다.
    - `fetch_area_list(lang, log)`: 타입마다 1쪽부터 `plan_pages`가 정한 쪽까지 `fp._call_and_save`로 받는다. 저장 위치는 `raw/name_backfill/<lang>_t<type>_p<page>.json`. 1쪽 `contenttypeid`를 검증하고(어긋나면 `TargetTypeMismatch`, 0건이면 "확인 불가" 기록), 받은 건수가 `totalCount`보다 적으면 경고한다. 1쪽 응답 직후 남은 필수 호출 수로 상한을 다시 점검한다.
    - `collect_area_lists(log)`: 언어를 `ja`, `en`, `zh-Hans`, `zh-Hant` 순으로 받고, 한 언어가 `FetchError`면 그 언어만 실패로 기록하고 계속한다. `--offline`에서 raw가 없으면 누락 경로를 모아 둔다.
    - `fp.REUSE_RAW`는 항상 켜고, `--offline`은 `fp.OFFLINE`으로 넘긴다.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 8.1, 8.2, 8.3, 8.6, 8.7_

  - [ ]* 4.2 속성 테스트: 저장된 쪽은 다시 호출하지 않는다
    - 가짜 `request_json`으로 요청 쪽 집합이 저장되지 않은 쪽과 같은지 확인한다.
    - **Property 12: 저장된 쪽은 다시 호출하지 않는다**
    - **Validates: Requirements 1.5, 8.1, 8.7**

  - [ ]* 4.3 수집 예시 테스트
    - 타입 검증(일치, 불일치 시 이후 호출 0건, 0건이면 "확인 불가"), raw 파일 이름과 `serviceKey` 미저장, 2쪽 실패 시 1쪽 파일 유지, 한 언어 실패 시 나머지 계속과 `api_error` 행, `--offline`의 호출 0회와 누락 경로 출력, `MAX_CALLS` 도달 시 추가 호출 0건·raw 보존·종료 코드 3 대상, 1쪽 `totalCount`로 초과 예상 시 2쪽 이후 미호출, 저장된 쪽만 있는 재실행의 호출 수 0.
    - 가짜 `request_json`과 `tmp_path`만 쓴다.
    - _Requirements: 1.2, 1.4, 1.6, 1.8, 1.9, 8.1, 8.2, 8.3, 8.4, 8.6, 8.7_

  - [x] 4.4 국문 기준 읽기와 복원 로직 구현
    - `load_kor`: `raw/<place_id>/ko.json`에서 국문 `contentid` 항목의 `{title, lat, lng}`를 읽는다. 없음·JSON 오류·title 또는 좌표 없음이면 `None`이고 `kor_raw_missing` 행을 남긴다. 국문 API는 부르지 않는다.
    - `apply_seed_fixes`: 메모리의 시드에서 `biff-square`의 `query`를 `"BIFF 광장"`으로 바꾸고, `jeonpo-cafe-street` 시드가 없으면 `RESTORE_SEEDS` 값(`category="street"`, `indoor=false`)으로 추가한다. 다른 시드는 그대로 둔다.
    - `resolve_restore`: `fp.search_keyword` 1회(재시도 1회, 타임아웃 5초) 후 부산 주소만 남기고 `fp.pick_kor`로 후보를 정한다. 0건·다수는 `no_candidate`·`multiple_candidates`, 호출 실패는 `search_failed`로 review에 남긴다.
    - `build_new_place`: 좌표가 있고 외국어 이름이 1개 이상일 때만 `Place.model_validate`로 검증한 장소·sources 항목을 만든다. 이름 0개는 `no_name_found`, `category`·`indoor` 없음은 `missing_category_or_indoor`로 남긴다. `nearest_station`은 `fp.nearest_station`으로 계산하고, 새 장소는 `places.json` 끝에 붙인다.
    - jeonpo-cafe-street는 `raw/jeonpo-cafe-street/ko.json`이 없을 때만 국문 조회를 1회 한다.
    - _Requirements: 3.4, 3.5, 3.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [ ]* 4.5 복원·시드 보정 예시 테스트
    - `load_kor` 4가지 경우, `apply_seed_fixes`(biff-square query 변경, 다른 시드 불변, jeonpo 시드가 있으면 추가 안 함), biff-square(검색 호출 1회에 `keyword="BIFF 광장"`, 후보 1건이면 추가, 0건·2건이면 미추가와 review, 호출 실패면 미추가), jeonpo-cafe-street(일치 있음/없음, `category`·`indoor` 없음)를 확인한다.
    - _Requirements: 3.4, 3.5, 5.1, 5.2, 5.3, 5.4, 5.7, 6.1, 6.3, 6.4, 6.5, 6.6_

  - [x] 4.6 파일 쓰기와 보고서 구현
    - `commit_files`: `{경로: 바이트}`를 임시 파일에 먼저 쓰고 `os.replace`로 교체하며, 도중 실패하면 메모리에 둔 원본 바이트로 되돌린다. `place_seeds.json`의 새 바이트도 같이 넣는다. 쓰기 없이 종료하는 경로에서는 시드 파일도 바뀌지 않는다.
    - `FillReport`와 `render_report`: 언어별 작업 전·후·증감 표, Target_Types 확인 근거, 해운대 3곳 ja 결과(채운 이름·일치 종류·거리 또는 사유), biff-square·jeonpo-cafe-street 추가 여부·이름·사유, 남은 빈 쌍(없으면 "없음")과 review 사유별 수, 서비스·작업별 호출 수와 `expected_calls`·`max_calls`, 연결 스크립트별 실행 여부, 경고를 담는다. 작업 전 수치는 어떤 파일도 쓰기 전에 측정하며 측정 실패 시 "측정 안 됨"으로 쓴다. 결과는 표준 출력과 `raw/name_backfill/fill_report.md`에 쓴다.
    - _Requirements: 4.8, 8.6, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

  - [ ]* 4.7 쓰기·보고서 예시 테스트
    - 두 번째 파일 교체를 실패시켜 세 파일(과 시드 파일)이 원본 바이트와 같음, `dump_review` 앞 3바이트가 BOM이고 `csv`로 읽어 같은 행, 작업 전 수치가 쓰기 전에 기록됨, `before=None`이면 "측정 안 됨", 해운대 3곳 ja 줄 형식, 호출 수가 정수로 출력됨.
    - _Requirements: 4.6, 4.8, 9.2, 9.5, 9.6, 9.7_

- [x] 5. `main` 연결
  - [x] 5.1 `main(argv)`로 전체 흐름 연결
    - CLI 인자 `--reuse-raw`, `--offline`을 받는다. 키(`DATA_GO_KR_KEY_DECODING`)가 없고 offline이 아니면 메시지 후 종료 코드 1.
    - 흐름: 입력 읽기 → 작업 전 수치·`Baseline_IDs`·`curation_overrides.json` 스냅샷 → 시드 보정 → 수집 → 기존 장소 채우기 → 복원 대상 처리 → `Place` 검증(실패 시 쓰기 없이 종료 1) → 병합 → `commit_files` → 연결 스크립트 실행 → 보고서.
    - 종료 코드: 0 정상, 1 일부 언어 실패·연결 스크립트 실패·검증 실패·쓰기 실패·`curation_overrides` 변경, 2 offline 누락, 3 호출 상한 중단. 코드 2·3과 Target_Types 불일치는 어떤 파일도 쓰지 않는다.
    - 연결 스크립트는 `main()`을 같은 프로세스에서 `run_chain`으로 부르고 실행 목록을 주입할 수 있게 한다. 새 장소의 `nearest_station`이 `stations.json`에 없거나 `build_congestion.PLACE_NAMES`에 없으면 보고서에 경고로 적는다.
    - 종료 시 실패 언어 수와 호출 수 표를 출력한다(상한 중단 시 한국어 중단 메시지 형식 포함).
    - _Requirements: 1.6, 2.12, 3.3, 4.8, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.1, 8.3, 8.5, 8.6, 8.7, 9.5_

  - [ ]* 5.2 `main` 통합 테스트 (가짜 호출, `tmp_path`)
    - 모듈 상수(`PLACES_PATH` 등)를 `monkeypatch`로 `tmp_path`에 돌리고, 합성 응답으로 전체 흐름을 확인한다. 이름 채움, 기존 이름 보존, sources·review 갱신, 새 장소 추가 시 연결 4개 순서 실행(가짜 러너), 실패 시 중단과 종료 코드 1, `curation_overrides` 변경 시 경고와 종료 코드 1, 종료 코드 2·3에서 쓰기 없음, 시드 파일 저장 여부를 검증한다. 실제 `app/data/`는 바뀌지 않음을 확인한다.
    - _Requirements: 2.12, 4.8, 7.1, 7.2, 7.3, 7.6, 8.3, 8.4, 10.6, 10.7_

  - [ ]* 5.3 정적 규칙 테스트
    - `backfill_names.py`가 `fetch_places`의 `pick_foreign`, `normalize_korean`, `strip_korean`, `haversine_m`을 import하고 같은 이름의 함수를 정의하지 않는지 소스 분석으로 확인한다.
    - _Requirements: 3.1, 3.3_

- [ ] 6. Checkpoint - 전체 테스트 통과 확인 (실제 API 호출 전 마지막 점검)
  - `backend/`에서 `uv run pytest tests/test_name_backfill.py`가 키 없이 모두 통과하는지 확인한다. 실제 API는 이 시점까지 한 번도 호출하지 않았어야 한다.
  - `git diff --stat -- backend/pyproject.toml backend/uv.lock backend/scripts/fetch_places.py backend/scripts/fetch_restaurants.py`가 비어 있는지 확인한다. 공용 파일도 바뀌지 않았는지 확인한다.
  - 통과하지 못하면 다음 작업으로 가지 않고 사용자에게 묻는다.

- [ ] 7. 전체 실행과 결과 보고 (실제 API 호출 수반, 마지막 쪽)
  - [ ] 7.1 전체 실행 1회 수행 ⚠️ 사용자 확인 후 실행
    - **실제 공공데이터 API를 호출하므로 실행 전에 사용자에게 확인을 받는다.** 확인 전에는 실행하지 않는다. 작업 6이 통과한 뒤에만 한다.
    - 확인 요청 때 예상 호출 수(`EXPECTED_CALLS=30`, 하한 17)와 상한(`MAX_CALLS=45`)을 알린다.
    - 확인 후 `backend/`에서 `uv run --env-file .env python -m scripts.backfill_names`를 정확히 1회 실행한다. 키 값은 출력하거나 파일에 쓰지 않는다.
    - 실패하거나 상한(종료 코드 3)으로 멈추면 원인을 보고하고, 다시 실행할 때는 사용자 확인 후 `--reuse-raw`로만 한다(저장된 쪽은 재호출 없음). 규칙만 바꾼 재생성은 `--offline`을 쓴다.
    - biff-square 시드 `query` 변경(`"BIFF 광장"`)과 연결 스크립트 재실행(새 장소가 생기면 4개 순서대로, 아니면 `build_curation`)이 이 실행에 포함된다.
    - commit과 push는 하지 않는다.
    - _Requirements: 5.1, 7.1, 7.3, 8.5, 8.7_

  - [ ] 7.2 결과 보고
    - 실행 후 `raw/name_backfill/fill_report.md`와 표준 출력을 바탕으로 다음을 사용자에게 보고한다.
      - 언어별(en, ja, zh-Hans, zh-Hant) 작업 전 / 작업 후 / 증감 표
      - 해운대 3곳(the-bay-101, busan-x-the-sky, sea-life-busan)의 ja 결과(이름·일치 종류·거리 또는 사유)
      - biff-square, jeonpo-cafe-street의 추가 여부, 이름 또는 사유, 추가한 시드
      - 작업 후에도 비어 있는 (장소, 언어) 쌍과 review 사유별 수
      - 서비스·작업별 API 호출 수와 합계(예상 30, 상한 45과 비교), 연결 스크립트별 실행 여부, 경고
    - 변경된 파일 목록을 알린다. `places.json`이 바뀌었으므로 프론트엔드 mock 복사본은 이 작업 범위 밖이며, 같은 PR에서 맞춰야 한다는 점만 안내한다(수정하지 않음).
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 8.6_

- [x] 8. 후속 정리 (places.json 35곳 반영)
  - 배경: name-backfill 실행으로 `backend/app/data/places.json`이 35곳이 되면서 테스트 3개가 실패한다. 이 작업은 작업 1.5~7.2와 파일·데이터가 겹치지 않으므로 그 작업들의 완료를 기다리지 않고 실행한다. 8.1 → 8.2 → 8.3 → 8.4 순서로 한 번에 하나씩 진행한다.
  - 수정 허용 범위: 8.1의 테스트 함수 2개, `backend/app/data/hours.json`, `backend/app/data/events.json`뿐이다. 그 밖의 테스트 함수·테스트 파일·`app/` 코드·스크립트는 바꾸지 않는다.
  - 외부 호출 한도: 새 API 호출은 8.2의 정확히 2회뿐이며 사용자가 이미 승인했다. 확인용 반복 호출은 하지 않는다. 8.3은 `--offline`이라 호출 0회다. 키 값은 출력·파일·로그에 쓰지 않고 `backend/.env`로만 다룬다.
  - 금지: commit과 push를 하지 않는다. 공용 파일(`backend/app/models/`, `docs/api-contract.md`, `backend/app/handler.py`, `.kiro/steering/team.md`)은 수정하지 않는다. 파일은 UTF-8(BOM 없음)로 저장하고, 명령은 Windows PowerShell 5.1 기준으로 쓴다.
  - 실행 순서 참고: 아래 의존성 그래프에서 작업 8은 기존 wave 뒤(wave 30~33)에 이어 붙였다. 도구가 작업 1.5~7.2 미완료 때문에 8.x를 아직 ready로 보지 않으면 사용자가 작업 8을 직접 시작한다.

  - [x] 8.1 실패 테스트 2개 고치기
    - 대상은 `backend/tests/test_agent_chat.py::test_place_name_falls_back_when_the_profile_language_has_none`과 `backend/tests/test_chat_support.py::test_place_name_falls_back_to_other_languages` 두 함수뿐이다. 두 파일은 A 담당 파일이므로 이 두 함수 밖은 바꾸지 않는다.
    - 원인: the-bay-101에 ja 이름이 생겨 "ja 이름이 없다"는 전제가 깨졌다.
    - 먼저 `place_name` 코드를 읽어 대체 순서(표시 언어 → en → 첫 값)를 확인하고, 기대값을 그 순서에 맞춘다.
    - 실제 `places.json`에서 ja 이름이 없는 장소를 찾아 쓰도록 바꾼다(현재는 busan-citizens-park뿐이고 en도 없다). 그런 장소가 없으면 테스트 안에서 ja를 뺀 `Place`를 만들어 검사한다.
    - 테스트의 의도(이름이 없는 언어일 때의 대체 동작 확인)는 바꾸지 않는다.
    - 보고: 고친 테스트 2개의 새 기대값.

  - [x] 8.2 hours.json에 biff-square, jeonpo-cafe-street 추가
    - `backend/scripts/fetch_hours.py`를 먼저 읽고 옵션을 확인한다. 대상을 이 두 곳으로 한정하고, 저장된 응답(raw)은 재사용하며, 새 API 호출이 2회를 넘지 않는 옵션 조합을 고른다.
    - `--dry-run`, `--offline` 같은 옵션이 있으면 실제 호출 전에 써서 대상이 이 두 곳뿐인지, 다른 장소의 `hours.json` 항목이 바뀌지 않는지 확인한다. 옵션이 없거나 호출이 2회를 넘을 수 있으면 실행하지 않고 사유를 보고한 뒤 멈춘다.
    - 실행 전에 `hours.json`을 읽어 두고, 실행 후 다른 장소의 항목이 그대로인지 비교한다.
    - 실제 호출은 정확히 한 번의 실행으로 한다. `backend/`에서 `uv run --env-file .env python -m scripts.fetch_hours <옵션>` 형식을 쓴다(작업 7.1 참고).
    - 보고: 두 곳의 운영시간 결과(받은 값 또는 없음과 사유), API 호출 수.

  - [x] 8.3 events.json 다시 만들기
    - 실행 전에 `backend/app/data/events.json`을 읽어 둔다.
    - `backend/`에서 `uv run python -m scripts.fetch_events --offline`을 실행해 `place_ids`와 `main_place_id`를 새 `places.json` 기준으로 다시 만든다. offline이므로 API 호출은 0회다.
    - 실행 후 이전 내용과 비교한다. 보고: 바뀐 행사(이름, 바뀐 `place_ids`와 `main_place_id`의 이전·이후). 바뀐 것이 없으면 "변경 없음"으로 적는다.

  - [x] 8.4 전체 테스트와 최종 보고
    - `backend/`에서 `uv run pytest -q`를 실행해 전부 통과하는지 확인한다. 통과하지 못하면 원인을 보고하고 멈춘다.
    - 처음 실패한 테스트 3개 중 8.1의 두 개를 뺀 나머지 하나가 무엇이었는지, 8.2와 8.3 중 무엇으로 해결됐는지 적는다. 8.1~8.3 후에도 실패가 남으면 그 테스트 이름과 원인을 적는다.
    - 최종 보고: 고친 테스트 2개의 새 기대값, 두 곳의 운영시간 결과, `events.json`에서 바뀐 행사, 전체 API 호출 수(8.2의 2회 이하 + 8.3의 0회), 변경된 파일 목록.

## Notes

- `*` 표시 작업은 선택(테스트)이며 건너뛸 수 있다. 구현 작업이 먼저 있어야 하므로, 건너뛰면 작업 6의 통과 확인 범위가 줄어든다는 점을 감안한다.
- 속성 테스트는 `hypothesis` 없이 `parametrize`와 고정 시드 난수로 구현한다. 의존성 파일은 건드리지 않는다.
- 작업 7.1은 사용자 확인 없이 실행하지 않는다. 작업 6 이전에는 실제 API 호출이 없다.
- 이 워크플로는 계획 문서 작성까지다. 구현은 tasks.md에서 작업을 시작하면 진행한다.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["1.3"] },
    { "id": 3, "tasks": ["1.4"] },
    { "id": 4, "tasks": ["1.5"] },
    { "id": 5, "tasks": ["1.6"] },
    { "id": 6, "tasks": ["1.7"] },
    { "id": 7, "tasks": ["1.8"] },
    { "id": 8, "tasks": ["1.9"] },
    { "id": 9, "tasks": ["1.10"] },
    { "id": 10, "tasks": ["1.11"] },
    { "id": 11, "tasks": ["1.12"] },
    { "id": 12, "tasks": ["2.1"] },
    { "id": 13, "tasks": ["2.2"] },
    { "id": 14, "tasks": ["2.3"] },
    { "id": 15, "tasks": ["2.4"] },
    { "id": 16, "tasks": ["2.5"] },
    { "id": 17, "tasks": ["2.6"] },
    { "id": 18, "tasks": ["4.1"] },
    { "id": 19, "tasks": ["4.2"] },
    { "id": 20, "tasks": ["4.3"] },
    { "id": 21, "tasks": ["4.4"] },
    { "id": 22, "tasks": ["4.5"] },
    { "id": 23, "tasks": ["4.6"] },
    { "id": 24, "tasks": ["4.7"] },
    { "id": 25, "tasks": ["5.1"] },
    { "id": 26, "tasks": ["5.2"] },
    { "id": 27, "tasks": ["5.3"] },
    { "id": 28, "tasks": ["7.1"] },
    { "id": 29, "tasks": ["7.2"] },
    { "id": 30, "tasks": ["8.1"] },
    { "id": 31, "tasks": ["8.2"] },
    { "id": 32, "tasks": ["8.3"] },
    { "id": 33, "tasks": ["8.4"] }
  ]
}
```
