# Implementation Plan: 맛집·대중교통 정보 도구 (info-tools)

## Overview

담당: B. 위에서부터 순서대로 하고, 작업 하나가 끝나면 실행·테스트 방법을 적고 멈춥니다.
수정 범위는 `backend/app/tools/restaurants.py`, `backend/app/tools/transit.py`, `backend/scripts/fetch_restaurants.py`, `backend/scripts/restaurant_seeds.json`, `backend/app/data/restaurants.json`, `backend/app/data/raw/restaurants/`, `backend/tests/test_restaurants.py`, `backend/tests/test_transit.py`입니다. `return_options.py`는 공개 헬퍼 추가만 합니다(열린 질문 5 확정 후). 공용 파일(`models/`, `api-contract.md`, `handler.py`, `team.md`), `agent.py`, `chat/`은 고치지 않습니다. 에이전트 연결 수정안은 `design.md`에 있습니다.
열린 질문(`design.md` 맨 아래) 중 1(외국어 `contentTypeId`), 4(서면 주변), 5(거리 헬퍼)는 해당 작업 전에 팀 답을 받습니다.

## Tasks

- [x] 1. 대중교통 정보 도구 `get_transit_info` (외부 API 없음, 먼저 끝낼 수 있음)
  - [x] 1.1 거리 헬퍼 확정: `return_options.py`에 공개 거리·도보 헬퍼를 추가할지 정한다(열린 질문 5). 추가하면 기존 `tests/test_return_options.py`가 그대로 통과하는지 확인
    - _Requirements: 6.4, 6.5_
  - [x] 1.2 `tools/transit.py`: 순수 함수 `transit_info(from_place_id, to_place_id, to_station)`. 입력 검증 순서(`missing_argument` → `place_not_found` → `same_place` → 도착 결정 → `station_not_found`/`no_station`), 역 연결, 도보·지하철·총 분 계산, `far_from_station` 경고
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9_
  - [x] 1.3 `basis`(규칙 값, `not_included`, 동해선·경전철 한계, `measured: false`)와 `@tool` 래퍼(`@tool` + `@_safe`), 영어 docstring(언제 쓰는지, 입력, 출력, 오류 코드, "about N minutes", 노선·환승·막차 단정 금지)
    - _Requirements: 6.10, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.1, 8.2, 8.3, 8.5_
  - [x] 1.4 `tests/test_transit.py`: 해운대 → 서면 값(`return_options.subway_minutes`와 같은 값), `to_place_id` 경로, 같은 역, 같은 장소, `OSIRIA`(해동용궁사), `nearest_station: null`, 환승역(서면), `to_station` 대소문자·공백·우선순위, `missing_argument`, 오류 형식
    - 실행: `uv run pytest -q tests/test_transit.py`
    - _Requirements: 5, 6, 7, 8.9_
  - [x]* 1.5 속성 테스트(Hypothesis 필요 여부는 열린 질문 7): 이동 시간 일치, 대칭성, 같은 역이면 0, 환승역 일치, ID 근거, 오류 형식
    - **Property 8: 이동 시간 일치(메타모픽)**
    - **Property 9: 대칭성**
    - **Property 10: 같은 역이면 0**
    - **Property 11: 환승역 일치**
    - **Property 12: ID 근거**
    - **Property 13: 오류 형식**
    - **Validates: Requirements 6.2, 6.5, 6.6, 6.7, 8.4, 5.5, 5.6**

- [x] 2. 체크포인트: 대중교통 도구
  - `uv run pytest -q`가 모두 통과하는지 확인하고, 막히면 질문한다. 결과 한 건을 눈으로 확인한다(`uv run python -c "from app.tools.transit import get_transit_info; print(get_transit_info(from_place_id='haeundae-beach', to_station='Seomyeon'))"`)

- [x] 3. 음식점 파일 형식과 읽기
  - [x] 3.1 `tools/restaurants.py`: Pydantic 모델(`RestaurantRecord`, `RestaurantTable`, `extra="forbid"`로 식단 필드 차단)과 읽기 함수(`lru_cache`, 경로 인자). 모델 위치는 열린 질문 6 확정 전까지 이 파일 안
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6_
  - [x] 3.2 직렬화 함수 `dump_restaurants`(정렬, 들여쓰기, 한국어 그대로)와 왕복·ID 유일성 테스트용 작은 예시 파일
    - _Requirements: 2.5, 2.7_
  - [x]* 3.3 속성 테스트: 파일 왕복, ID 유일성
    - **Property 5: 파일 왕복**
    - **Property 6: ID 유일성**
    - **Validates: Requirements 2.4, 2.7**

- [x] 4. 맛집 도구 `get_restaurants`
  - [x] 4.1 `restaurants_near(place_id, radius_m, limit)`: 반경 판단(반올림 전 거리), 정렬 `(distance_m, restaurant_id)`, `limit`, `total_in_radius`, `walk_min`
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7_
  - [x] 4.2 오류 처리: `place_not_found`, `restaurants_not_collected`, `invalid_argument`, `data_unavailable`
    - _Requirements: 3.8, 3.9, 3.10, 3.11, 8.2_
  - [x] 4.3 `basis`(출처, 수집일, `diet_info: "not_available"`, 직선거리 추정, 영업시간·가격·식단 미포함 문장)와 `@tool` 래퍼, 영어 docstring(식단 정보 없음, 가게에 확인하라는 안내, 평점·순위 없음, 오류 코드)
    - _Requirements: 3.6, 3.12, 4.1, 4.2, 4.3, 4.4, 4.5, 8.1, 8.3, 8.5_
  - [x] 4.4 `tests/test_restaurants.py`: 임시 `restaurants.json`으로 거리·정렬·`limit`·경계 반경·빈 결과·모든 오류 코드·식단 필드 없음
    - 실행: `uv run pytest -q tests/test_restaurants.py`
    - _Requirements: 3, 4, 8.9_
  - [x]* 4.5 속성 테스트: 반경 불변식, 반경 단조성, 정렬 결정성, 식단 비주장
    - **Property 1: 반경 불변식**
    - **Property 2: 반경 단조성**
    - **Property 3: 정렬 결정성**
    - **Property 4: 식단 비주장**
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 4.1, 4.2**

- [x] 5. 음식점 수집 스크립트 (API 키 필요, 호출 수 확인 후 실행)
  - [x] 5.1 선행 확인 1회: 국문 음식점 한 곳과 외국어 서비스 응답을 받아 `contentTypeId`, 분류 코드(`lclsSystm1~3`), 이름 형식을 확인하고 열린 질문 1·2를 정리해 팀에 알린다. 이 단계는 호출 10회 이내
    - _Requirements: 1.2, 1.4_
  - [x] 5.2 `scripts/fetch_restaurants.py`: 시드 검증(`places.json`에 있는 ID만), Anchor별 국문 수집(반경 1000m, 페이지), 외국어 수집, `fetch_places`의 `pick_foreign` 재사용, 검토 목록, `CUISINE_BY_CLASS`, 합치기·정렬, `--offline`·`--reuse-raw`, 키 없음 종료 코드 1, 요약 출력
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 2.4, 2.5_
  - [x] 5.3 `restaurant_seeds.json`에 데모 Anchor `haeundae-beach`, `jagalchi-market`, `gamcheon-village`를 넣는다. 서면 주변은 열린 질문 4 확정 후
    - _Requirements: 1.9_
  - [x] 5.4 스크립트 테스트(`test_restaurants.py`에 추가): `request_json`을 고정 응답으로 바꿔 외국어 일치(exact·contains·불일치), 합치기, 오프라인 재현, 호출 수, 키가 raw에 없음, 네트워크 차단
    - _Requirements: 1.2, 1.3, 1.5, 1.6, 1.7_
  - [x]* 5.5 속성 테스트: 수집 멱등성
    - **Property 7: 수집 멱등성**
    - **Validates: Requirements 1.6, 2.5**
  - [x] 5.6 실제 수집 실행(`uv run --env-file .env python -m scripts.fetch_restaurants`), `restaurants.json`·검토 목록 확인, 데모 Anchor가 모두 비어 있지 않은지 확인. `raw/restaurants/`와 `.env`는 커밋하지 않는다
    - _Requirements: 1.10, 2.1, 2.2_

- [x] 6. 체크포인트: 맛집 도구
  - `uv run pytest -q`가 모두 통과하는지 확인하고, 실제 데이터로 `get_restaurants('haeundae-beach')` 결과를 눈으로 확인한다(이름 언어, 거리, `basis`)

- [ ] 7. 문서와 연결 수정안 전달
  - [x] 7.1 `.kiro/steering/data-rules.md`에 「음식점」·「대중교통」 절 추가(열린 질문 9 확정 후): 수집 명령, 파일 형식, 한계(식단·영업시간 없음, 동해선 없음, 추정)
    - _Requirements: 7.4, 4.1_
  - [ ] 7.2 PR 설명에 `design.md`의 「에이전트 연결 수정안」(A의 `chat/tools.py`·`chat/answer.py`, D의 프롬프트 한 줄)을 요약해 담당자에게 전달. `agent.py`와 `chat/`은 수정하지 않는다
    - _Requirements: 8.8_

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "3.1", "5.1"] },
    { "id": 1, "tasks": ["1.2", "3.2", "5.2"] },
    { "id": 2, "tasks": ["1.3", "3.3", "4.1", "5.3", "5.4"] },
    { "id": 3, "tasks": ["1.4", "4.2", "5.5"] },
    { "id": 4, "tasks": ["1.5", "4.3", "5.6"] },
    { "id": 5, "tasks": ["4.4", "4.5", "7.1", "7.2"] }
  ]
}
```

## Notes

- `*`가 붙은 작업은 선택입니다. 속성 테스트는 Hypothesis가 이미 있거나 팀이 추가를 허용할 때 합니다. 없으면 같은 검사를 대표 예시 여러 개로 `tests/`에 씁니다.
- 순서 이유: 대중교통 도구는 외부 API가 필요 없어 먼저 끝낼 수 있고, 맛집은 수집 전에 파일 형식과 도구를 고정해 두면 수집 결과를 바로 검증할 수 있습니다.
- 커밋 금지: `.env`, 키 값, `raw/restaurants/`(원본 응답), 카카오 경로 결과.
