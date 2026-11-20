# 구현 작업: Schedule Guardian

담당: D (Guardian). 위에서부터 순서대로 하고, 작업 하나가 끝나면 실행·테스트 방법을 적고 멈춥니다.
모든 작업은 `backend/app/guardian/`과 `backend/tests/` 안에서 합니다.
시간 배정은 노션 「역할 분담과 타임테이블」 기준입니다: 작업 1은 목 저녁, 2~4는 금 09:30~12:00, 5~7은 금 13:00~18:00, 11은 금 21:00~24:00.

- [x] 1. 기반 코드
  - `thresholds.py` 기준값 상수 작성 (데이터 담당과 함께)
  - `context.py`에 `CheckContext` 모델 작성 (도구 반환 형식은 도구 담당과 확정)
  - 테스트용 `context` 고정 데이터 작성 (`sample_plan.json` 기준)
  - _요구사항: 2, 6.3_

- [x] 2. 점검 규칙 4개 (`rules.py`)
  - [x] 2.1 `check_crowded`: 집중률 기준, 요일 규칙, 행사 가중
  - [x] 2.2 `check_rain`: 실외 장소, 체류 시간대 강수확률·강수 비율
  - [x] 2.3 `check_closed`: 휴무일, 운영시간
  - [x] 2.4 `check_tight_transfer`: 이동 여유 시간
  - _요구사항: 2.1~2.7, 2.9_

- [x] 3. `check.py`의 `check_plan()`
  - 결정적 `issue_id`, 고정 일정 `low` 제한, 정렬, 데이터 없는 규칙 건너뛰기
  - _요구사항: 2.8, 2.10, 3.1, 6.4_

- [x] 4. 점검 단위 테스트
  - 규칙마다 1개 이상, `check_plan`의 `issue_id`·고정 일정·정렬·건너뛰기
  - `uv run pytest -q tests/test_guardian.py`
  - _요구사항: 2, 3.1, 6.4_

- [x] 5. 보전 지표와 해결안 탐색
  - [x] 5.1 `metrics.py` 보전 지표
  - [x] 5.2 `repair.py`의 `try_move_time` (이웃 Stop 체류 시간 조정 포함)
  - [x] 5.3 `try_reorder`
  - [x] 5.4 `try_replace`
  - [x] 5.5 `try_remove`
  - [x] 5.6 고정 일정 검증, 재점검 필터, 정렬, 상위 3개, `places` 목록
  - _요구사항: 3.2, 4.1~4.9_

- [x] 6. 지연 재조정 ("늦었어요")
  - 기준 시각 이후 비고정 Stop 재조정, 고정 일정 유지, 보전 지표
  - _요구사항: 7_

- [x] 7. 데모 테스트 5개 통과
  - `design.md` 테스트 표의 케이스 전부 + 데모 장면 테스트 (케이스 목록은 데모 대본 기준으로 확정)
  - `uv run pytest -q tests/test_guardian.py`
  - 이 작업이 끝나기 전에는 API 연결로 넘어가지 않습니다.

- [x] 8. `context.py`의 `build_context(plan)`
  - `app/tools/lookup.py` 조회 함수로 `context` 조립, `USE_MOCK=1`에서 동작 확인
  - _요구사항: 1.2, 6.3, 6.4_

- [x] 9. `handler.py` 연결 PR (공용 파일, 뼈대 담당자 리뷰)
  - `TODO(Guardian 담당)` 자리를 `build_context` → `check_plan` → `propose_repairs` 호출로 교체
  - `uv run python -m scripts.local_invoke`로 `/plan/check` 응답 확인
  - _요구사항: 1.1, 1.2_

- [x] 10. 성능 확인
  - `check_plan` 300ms, `propose_repairs` 1초 이내 (Stop 5곳, 미리 조립한 `context`)
  - _요구사항: 6.1, 6.2_

- [x] 11. 예약 점검 (EventBridge)
  - 예보 갱신 시각에 `check_plan`을 실행하고 결과를 DynamoDB에 저장
  - 로직은 `guardian/scheduled.py`에 작성. Lambda 연결·스케줄(`infra/`)과 DynamoDB 저장 형식은 A와 확정 후 진행
  - _요구사항: 8_
