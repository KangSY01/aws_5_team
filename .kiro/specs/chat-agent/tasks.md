# Implementation Plan: 대화 에이전트

## Overview

담당: 에이전트·도구. 위에서부터 순서대로 하고, 작업 하나가 끝나면 실행·테스트 방법을 적고 멈춥니다.

## Tasks

- [ ] 1. 모델과 고정 응답 경로
  - `agent.py`의 `build_model()` 구현 (`config.MODEL_ID`, `config.BEDROCK_REGION`, `max_tokens`, 스트리밍 끔)
  - 판단용(작은 모델)·답변용(큰 모델) 모델 객체 두 개를 모듈 로드 때 1회씩 생성. 답변용은 `MODEL_ID`를 유지
  - 판단용 모델 ID는 새 환경 변수 `MODEL_ID_JUDGE`로 읽고, 추가 시 `config.py`와 `backend/.env.example`을 같은 변경에서 함께 수정. 작은 모델 ID 기본값은 대회 계정에서 확인한 뒤 결정(이 작업에서 임의로 확정하지 않음)
  - `FAKE_LLM=1`이면 `run_chat`이 고정 `ChatResponse`를 돌려주도록 구현
  - `FAKE_LLM=1`이면 두 단계 모두 Bedrock을 호출하지 않음: 판단 단계는 고정 JSON 도구 계획, 답변 생성 단계는 `chat_response.json` 형식의 고정 응답
  - `BEDROCK_REGION`이 `ap-northeast-2`가 아니면 한국어 오류 로그를 남기고 예외 발생 (두 모델 모두 적용)
  - Bedrock 호출에 타임아웃 5초, 재시도 1회 적용
  - `FAKE_LLM=1`, `USE_MOCK=1`에서 AWS 자격 증명 없이 테스트 통과 확인
  - 테스트: `uv run pytest -q`
  - _요구사항: 6.1, 6.2, 6.6, 6.7, 7.1, 7.4, 11.11, 11.12_

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
  - `replace_stop`, `add_stop`은 같은 요청의 `search_places` 결과에 있는 `place_id`만 허용
  - 단위 테스트: 각 도구 1개 이상, 고정 일정 거부 1개
  - _요구사항: 3.1, 3.3, 3.7, 4.5_

- [ ] 4. 시스템 프롬프트와 `run_chat`
  - `prompts.py` 작성: 판단용 프롬프트(JSON만 출력, 등록된 도구만, `place_id` 추측 금지)와 답변용 프롬프트를 분리
  - Agent는 요청마다 생성(판단 단계·답변 생성 단계 각각), 모델 객체는 작업 1에서 만든 것을 재사용, 조회 도구 호출은 요청당 5개 이하. 메시지 한 건당 Bedrock 호출은 정확히 2회
  - 판단 JSON(도구 계획: `intent`, `tools[].name`·`args`, 선택 `reason_note`)의 내부 Pydantic 모델을 `agent.py` 또는 별도 내부 모듈에 정의(`backend/app/models/`는 수정하지 않음)
  - 판단 JSON 스키마 검증, 실패 시 판단 단계 1회 재시도, 재시도도 실패하면 도구 실행 없이 오류 형식으로 답하고 일정 저장 안 함
  - 도구 계획 검증: 미등록 도구와 `places.json`에 없는 `place_id` 항목은 실행하지 않고 한국어 경고 로그
  - 조회 도구 병렬 실행(5개 이하, 초과분 미실행): 도구별 타임아웃 5초·재시도 1회, 실패는 오류 결과로 표시하고 나머지로 계속(부분 실패 허용)
  - `plan_edit` 도구는 조회 도구 병렬 실행이 끝난 뒤 계획 순서대로 순차 실행, `locked: true` 거부와 3.5~3.7 규칙 유지
  - 답변 생성 단계 입력 구성: 프로필, 현재 일정, 도구 결과, 의도만 전달(스트리밍 없음)
  - `sources`, `plan_changes`는 답변 생성 단계 LLM 출력이 아니라 도구 결과에서 코드로 생성, 장소 ID 검증
  - 조회 도구가 5개를 넘으면 초과분은 실행하지 않고 확보한 결과로 `ChatResponse` 생성
  - `sources`: 같은 `tool`·`id`는 처음 순서로 한 번만, 성공한 도구 결과에 있는 항목만, `title`은 프로필 언어 우선·없으면 다른 언어나 ID로 대체
  - `plan_changes`: 실제로 바뀐 Stop만 넣고 `before`는 요청 시작 시점의 Stop과 일치
  - 저장 전 최종 검증: `locked: true`인 Stop의 `place_id`, `start`, `end` 불변 확인
  - 답변 검증: `place_id`, Locked Stop 유지, `ChatResponse` 검증. 모델 출력이 통과하지 못하면 반환하지 않고 답변 생성 단계를 1회 재시도, 재시도도 실패하면 오류 형식으로 답하며 일정 저장 안 함
  - 일정 상태 접근: `plan_id`로 `app/storage` 읽기(`USE_MOCK=1`이면 `sample_plan.json`), 없으면 `plan_not_found`로 변환될 예외, 현재 일정은 요청 범위로만 도구에 전달, `StopChange` 1건마다 저장 반영, 저장 실패 시 오류 형식
  - 로그와 주석은 한국어, 키·메시지 원문·프로필 값은 로그에 넣지 않음
  - _요구사항: 1.1~1.3, 3.4~3.6, 4.1~4.7, 5.1~5.3, 6.5, 6.8, 9.1~9.5, 10.1, 10.2, 11.1~11.10_

- [ ] 5. 일정 생성
  - 시각 계산 함수 위치를 도구 담당과 정하고 구현
  - `plan_id`가 없을 때 새 일정 생성, 저장은 `app/storage` 사용
  - 서로 다른 Stop의 시간 구간이 겹치지 않고, `start`가 `end`보다 앞서며 시간대 오프셋 포함 ISO 8601 형식
  - 유효하지 않은 `place_id`는 제외하고 한국어 경고 로그 후 나머지로 계속
  - 유효한 장소가 0개이면 일정 미생성, 안내 문구, `plan_changes` 빈 목록
  - `FAKE_LLM=1`, `USE_MOCK=1`이면 같은 입력에 같은 방문 순서와 `start`·`end`
  - _요구사항: 2.1~2.8_

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

- [ ] 9. 테스트 보강
  - `backend/pyproject.toml` dev 의존성에 `hypothesis` 추가
  - `bedrock` 마커 등록, 기본 pytest 실행에서 제외
  - `design.md` 테스트 표의 케이스를 `backend/tests/`에 구현 (Bedrock 케이스는 `bedrock` 마커)
  - `design.md` Testing Strategy의 새 케이스 추가: 두 단계 `FAKE_LLM` 고정 응답, 판단 단계 잘못된 JSON(1회 재시도 후 오류), 병렬 중 도구 한 개 실패, 조회 도구 6개 이상(5개만 실행), 미등록 도구·없는 `place_id`, 정상 경로에서 Bedrock 호출 정확히 2회(가짜 클라이언트로 횟수 확인)
  - property-based test 2종, 각 100회 이상: Locked Stop 불변, 일정 생성 정합성(시간 겹침 없음, 모든 `place_id`가 `places.json`에 존재)
  - property-based test 4종 추가, 각 100회 이상: Property 7(Bedrock 호출 정확히 2회), Property 8(미등록 도구·없는 `place_id` 미실행), Property 9(병렬 조회 도구 5개 이하), Property 10(`sources`·`plan_changes`는 도구 결과에서만 생성)
  - 기본 실행이 AWS 자격 증명, `DATA_GO_KR_KEY`, 네트워크 없이 통과하고 기존 베이스라인 테스트 11개도 통과하는지 확인
  - _요구사항: 10.4, 10.5, 10.6, 10.7, 11.1, 11.2, 11.3, 11.4, 11.5, 11.9, 11.12_

- [ ] 10. 단계별 소요 시간 로그와 eval 기록
  - `run_chat`이 판단 단계·답변 생성 단계 각각의 소요 시간(밀리초)과 실행한 도구 이름·성공 여부를 한국어 로그로 남김. 사용자 메시지 원문, 프로필 값, 키는 넣지 않음
  - Agent 실행이 끝나면 도구 이름별 호출 횟수를 한국어 로그 1건으로 남기고, 오류로 끝났으면 오류 종류도 포함
  - `backend/eval/run_eval.py` 결과 CSV에 판단 단계 시간과 답변 생성 단계 시간을 각각 기록하고 전체 응답 시간을 15초 목표와 비교
  - 단위 테스트: `caplog`로 로그 항목과 민감 값 미포함 확인
  - _요구사항: 6.3, 8.1, 10.2, 10.3, 11.13_

## Notes

- 각 작업은 요구사항 번호로 추적합니다.
- 같은 파일을 쓰는 작업은 서로 다른 wave에 둡니다.
- 이동 시간·행사·먹거리 도구와 일정 전달 방식은 도구 담당과 합의가 필요하며, 작업 2·3의 문구를 유지하고 새 구현 작업으로 만들지 않습니다.
- 작업 10은 `agent.py`와 `run_eval.py`를 함께 고치므로 작업 4·5·8 이후에 둡니다.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["2.2"] },
    { "id": 3, "tasks": ["2.3"] },
    { "id": 4, "tasks": ["2.4"] },
    { "id": 5, "tasks": ["3"] },
    { "id": 6, "tasks": ["4"] },
    { "id": 7, "tasks": ["5"] },
    { "id": 8, "tasks": ["6"] },
    { "id": 9, "tasks": ["7"] },
    { "id": 10, "tasks": ["8", "9"] },
    { "id": 11, "tasks": ["10"] }
  ]
}
```
