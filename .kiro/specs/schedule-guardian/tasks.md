# 구현 작업: Schedule Guardian

담당: Guardian. 위에서부터 순서대로 하고, 작업 하나가 끝나면 실행·테스트 방법을 적고 멈춥니다.
모든 작업은 `backend/app/guardian/`과 `backend/tests/` 안에서 합니다.

- [ ] 1. 기반 코드
  - `thresholds.py` 기준값 상수 작성
  - `context.py`에 `CheckContext` 모델 작성 (도구 반환 형식은 도구 담당과 확정)
  - 테스트용 `context` 고정 데이터 작성 (`sample_plan.json` 기준)
  - _요구사항: 2, 6.3_

- [ ] 2. 점검 규칙 4개 (`rules.py`)
  - [ ] 2.1 `check_crowded`: 집중률 기준, 요일 규칙, 행사 가중
  - [ ] 2.2 `check_rain`: 실외 장소, 체류 시간대 강수확률·강수 비율
  - [ ] 2.3 `check_closed`: 휴무일, 운영시간
  - [ ] 2.4 `check_tight_transfer`: 이동 여유 시간
  - 규칙마다 단위 테스트 1개 이상
  - _요구사항: 2.1~2.7, 2.9_

- [ ] 3. `check.py`의 `check_plan()`
  - 결정적 `issue_id`, 고정 일정 `low` 제한, 정렬, 데이터 없는 규칙 건너뛰기
  - _요구사항: 2.8, 2.10, 3.1, 6.4_

- [ ] 4. `metrics.py` 보전 지표
  - _요구사항: 4.7_

- [ ] 5. `repair.py`의 `propose_repairs()`
  - [ ] 5.1 `try_move_time` (이웃 Stop 체류 시간 조정 포함)
  - [ ] 5.2 `try_reorder`
  - [ ] 5.3 `try_replace`
  - [ ] 5.4 `try_remove`
  - [ ] 5.5 고정 일정 검증, 재점검 필터, 정렬, 상위 3개, `places` 목록
  - _요구사항: 3.2, 4.1~4.9_

- [ ] 6. `design.md` 테스트 표의 케이스 전부 통과
  - `uv run pytest -q tests/test_guardian.py`
  - 이 작업이 끝나기 전에는 API 연결로 넘어가지 않습니다.

- [ ] 7. `context.py`의 `build_context(plan)`
  - `app/tools/lookup.py` 조회 함수로 `context` 조립, `USE_MOCK=1`에서 동작 확인
  - _요구사항: 1.2, 6.3, 6.4_

- [ ] 8. `handler.py` 연결 PR (공용 파일, 뼈대 담당자 리뷰)
  - `TODO(Guardian 담당)` 자리를 `build_context` → `check_plan` → `propose_repairs` 호출로 교체
  - `uv run python -m scripts.local_invoke`로 `/plan/check` 응답 확인
  - _요구사항: 1.1, 1.2_

- [ ] 9. 성능 확인
  - `check_plan` 300ms, `propose_repairs` 1초 이내 (Stop 5곳, 미리 조립한 `context`)
  - _요구사항: 6.1, 6.2_
