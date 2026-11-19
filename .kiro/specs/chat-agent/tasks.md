# 구현 작업: 대화 에이전트

담당: 에이전트·도구. 위에서부터 순서대로 하고, 작업 하나가 끝나면 실행·테스트 방법을 적고 멈춥니다.

- [ ] 1. 모델과 고정 응답 경로
  - `agent.py`의 `build_model()` 구현 (`config.MODEL_ID`, `config.BEDROCK_REGION`, `max_tokens`, 스트리밍 끔)
  - `FAKE_LLM=1`이면 `run_chat`이 고정 `ChatResponse`를 돌려주도록 구현
  - 테스트: `uv run pytest -q`
  - _요구사항: 6.1, 6.2, 7.1_

- [ ] 2. 조회 도구 구현 (`tools/lookup.py`)
  - [ ] 2.1 `search_places`: `places.json`에서 `query`·`category`·`indoor`로 걸러 `Place` dict 목록 반환
  - [ ] 2.2 `get_weather`: 기상청 단기예보, `USE_MOCK=1`이면 샘플 반환. 반환 형식 확정
  - [ ] 2.3 `get_crowd`: 집중률 + 요일 규칙 + 행사 가중. 반환 형식 확정
  - [ ] 2.4 영업 정보·이동 시간 조회 도구 추가
  - 외부 API는 타임아웃 5초, 재시도 1회. 실패 시 오류 dict 반환
  - _요구사항: 4.1, 4.4, 7.2_

- [ ] 3. 부분 수정 도구 구현 (`tools/plan_edit.py`)
  - 현재 일정을 도구에 넘기는 방법 결정 후 `design.md`에 기록
  - `locked: true` 거부, 없는 `place_id` 거부, 결과는 `StopChange`
  - 단위 테스트: 각 도구 1개 이상, 고정 일정 거부 1개
  - _요구사항: 3.1, 3.3, 4.5_

- [ ] 4. 시스템 프롬프트와 `run_chat`
  - `prompts.py` 작성, Agent는 요청마다 생성, 도구 반복 5회
  - `sources`, `plan_changes` 모으기, 장소 ID 검증
  - _요구사항: 1.1~1.3, 3.4, 4.1~4.5, 5.1~5.3_

- [ ] 5. 일정 생성
  - 시각 계산 함수 위치를 도구 담당과 정하고 구현
  - `plan_id`가 없을 때 새 일정 생성, 저장은 `app/storage` 사용
  - _요구사항: 2.1~2.4_

- [ ] 6. Guardian 연결
  - 혼잡·비·휴무·빠듯한 이동 수정 요청에 `propose_repairs` 첫 해결안 사용
  - Guardian 스펙 작업 4 이후에 진행
  - _요구사항: 3.2_

- [ ] 7. `handler.py` 연결 PR (공용 파일, 뼈대 담당자 리뷰)
  - `TODO(에이전트 담당)` 자리를 `run_chat(request)` 호출로 교체
  - `uv run python -m scripts.local_server`로 프론트엔드에서 확인

- [ ] 8. 평가
  - `backend/eval/queries.json` 작성, `run_eval.py` 실행, 결과 CSV를 발표 자료에 반영
  - _요구사항: 8.1, 8.2_
