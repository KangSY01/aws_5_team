# 구현 작업: 축제 후 귀가 분산 (return-dispersal)
담당: B. 위에서부터 순서대로 하고, 작업 하나가 끝나면 실행·테스트 방법을 적고 멈춥니다.
수정 범위는 `backend/app/tools/return_options.py`, `backend/app/tools/lookup.py`(`get_events` 필드 추가만), `backend/app/data/stations.json`, `backend/app/data/events.json`, `backend/scripts/build_stations.py`, `backend/scripts/fetch_events.py`, `backend/tests/test_return_options.py`, `backend/tests/test_lookup.py`입니다. 공용 파일(`models/`, `api-contract.md`, `handler.py`, `team.md`)과 `agent.py`는 고치지 않습니다.
기능 동결(토 00:00) 전에 머지되지 않으면 장면 7은 슬라이드 캡처로 대체합니다(`docs/demo-readiness.md`).
열린 질문 5개는 확정했습니다(`design.md` 「확정된 결정」).

- [x] 1. 출처 형식 확인
  - 다른 도구가 `sources`를 어떻게 담는지 확인해 반환 형식에 맞춘다
  - _요구사항: 설계 「반환 형식」_
- [x] 2. 행사 대표 장소 `main_place_id`
  - [x] 2.1 `fetch_events.py`: `place_ids` 중 행사 좌표와 가장 가까운 장소를 `main_place_id`로 저장(동거리는 `place_id` 사전순, 비면 `null`)
  - [x] 2.2 `uv run python -m scripts.fetch_events --offline`으로 `events.json`을 다시 만들어 14개 행사의 값을 확인(빛축제는 `sea-life-busan`, 행사 1개는 `null`)
  - [x] 2.3 `lookup.get_events`가 `main_place_id`를 돌려주도록 필드만 추가하고 docstring(영어)에 설명을 추가
  - [x] 2.4 `tests/test_lookup.py`에 검사 추가. Guardian 테스트(`uv run pytest -q tests/test_guardian_context.py`)도 통과하는지 확인
  - _요구사항: 1_
- [x] 3. 역 표
  - `build_stations.py`: `busan_stations.csv` → `stations.json`(환승역 합치기, 표에 없는 `nearest_station` 경고)
  - `uv run python -m scripts.build_stations`로 만들고 `stations.json`을 확인(115행에서 환승역 6곳을 합친 수, `Seomyeon` 한 항목에 `lines` 1·2호선)
  - 카카오·외부 API 호출 없음
  - _요구사항: 2.5, 4.5, 6.1, 6.3_
- [x] 4. 순수 계산 함수 (`return_options.py`, `@tool` 없이)
  - [x] 4.1 입력 검증과 행사 찾기(`event_name`·`place_id`), `get_events`의 일반 함수 호출 방식 정하기
  - [x] 4.2 도착역 결정: `destination_station`(정규화) → `destination_place_id`의 `nearest_station` → 기본값 `DEFAULT_DESTINATION_STATION`(`"Seomyeon"`), `is_default`·`destination.place_id` 채우기, `station_not_found`·`no_station`·`same_station`
  - [x] 4.3 역 사이 이동 시간 계산: 역 좌표 + `travel_times.json`의 `rule`(경로 거리 × 1.3, 지하철 25km/h + 10분, 도보 4.5km/h, 올림). `baseline.minutes`와 `extra_min`이 같은 함수를 쓰게 한다. 해운대→서면 39분, 동백 +15, 중동 +20(어림값)과 맞는지 확인
  - [x] 4.4 혼잡 역(`main_place_id`의 역 1개)과 혼잡 시간대 계산(자정 넘김, 진행 시간 모르는 행사)
  - [x] 4.5 제안 만들기: (a) 시각, (b) 걸어서 20분 이내 다른 역, `extra_min`, 정렬·상한
  - _요구사항: 2, 3, 4, 5.1~5.3_
- [x] 5. 순수 함수 단위 테스트
  - `tests/test_return_options.py`: 장면 7 재현(`event_name`만, `place_id`만), 도착역 기본값·`destination_place_id`·우선순위·정규화, 이동 시간 어림값, 시간대 경계, 자정 넘김, 혼잡 아닌 출발이면 `options: []`, `no_time_basis`, `no_event_station`, `event_not_found`, `ambiguous_event`, `station_not_found`, `no_station`, `same_station`, `other_line` 없음
  - `uv run pytest -q tests/test_return_options.py`
  - _요구사항: 2, 3, 4_
- [x] 6. `@tool` 도구와 반환 형식
  - `get_return_options` 작성(`@tool` + `@_safe`, 영어 docstring: 언제 쓰는지, 입력, 출력, 규칙 기반 추정, 혼잡 시간대는 가정, 이동 시간은 역 좌표 어림값, 막차 모름, 도착역 기본값 Seomyeon)
  - `destination_station` 기본값은 `None`(생략과 직접 지정을 구별), docstring에는 "기본값 Seomyeon"이라고 적는다
  - 반환 dict가 `design.md` 「반환 형식」과 같은지 확인, `ratio`·혼잡 등급 필드 없음, `basis`에 가정 시간대와 이동 시간 규칙 값 포함
  - 기존 `tests/test_lookup.py`의 도구 docstring 검사와 같은 방식의 검사를 추가
  - _요구사항: 3.5~3.7, 5.3~5.6, 7_
- [x] 7. 금지 사항·무결성 테스트
  - 카카오 문자열·API 주소 검사, 네트워크 차단 상태에서 실행, 응답의 장소 ID·역 이름이 데이터에 있는지
  - `uv run pytest -q`(전체)로 기존 테스트가 깨지지 않았는지 확인
  - _요구사항: 2.10, 6, 7.2, 7.4_
- [x] 8. 데모 확인과 연결 안내
  - `scripts/demo_lookup.py`에 장면 7 호출 예를 추가하거나(B 소유 스크립트면), 실행 명령만 안내한다
  - 수정안 정리(직접 고치지 않음): `agent.py` 도구 등록(A), `chat-agent/design.md` `get_events` 행, `data-rules.md` 「행사」·역 표 항목
  - 구현 후 확인한 값으로 `docs/demo-readiness.md` 장면 7 행 갱신을 제안한다
  - _요구사항: 범위 밖 항목_
