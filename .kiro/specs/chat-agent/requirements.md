# Requirements Document

## Introduction
대화 에이전트는 외국인 관광객의 메시지에 사용자 언어로 답하고, 채팅으로 일정을 만들고 고치는 기능입니다.
Strands Agents로 작성하고 `POST /chat`을 처리하는 Lambda(`app.handler.handler`) 안에서 실행합니다.
요청·응답 형식은 `docs/api-contract.md`의 `POST /chat`과 `backend/app/models/api.py`의 `ChatRequest`, `ChatResponse`를 따릅니다.

## Glossary

- **시스템**: `POST /chat`을 처리하는 대화 에이전트. Lambda(`app.handler.handler`) 안에서 실행되는 Strands Agent와 주변 코드를 합친 것입니다.
- **Agent**: Strands Agents로 만든 에이전트. 요청마다 생성하며 도구를 호출해 답을 만듭니다.
- **Plan**: 하루 일정. Stop 목록과 프로필을 가집니다 (`backend/app/models/plan.py`).
- **Stop**: Plan 안의 방문 한 건. `stop_id`, `place_id`, `start`, `end`, `locked`를 가집니다.
- **Locked Stop**: `locked: true`인 Stop.
- **StopChange**: Stop 하나의 변경 기록. `stop_id`, `before`, `after`를 가지며, `before`가 `null`이면 추가, `after`가 `null`이면 제거입니다.
- **Place**: `backend/app/data/places.json`의 장소. 다국어 이름 `names`를 가집니다.
- **ChatRequest / ChatResponse**: `POST /chat`의 요청·응답 모델 (`backend/app/models/api.py`).
- **sources**: `ChatResponse`에서 답변의 근거가 된 도구 결과 목록. 항목은 `tool`, `id`, `title`을 가집니다.
- **plan_changes**: `ChatResponse`에서 이번 응답으로 일정에 적용된 `StopChange` 목록.
- **plan_edit 도구**: 일정 부분 수정 도구 `replace_stop`, `add_stop`, `remove_stop`, `move_stop`.
- **search_places**: 장소를 검색하는 조회 도구.
- **Guardian**: LLM 없이 일정을 점검하고 해결안을 만드는 순수 파이썬 모듈. `propose_repairs`는 해결안을 만드는 함수입니다.
- **집중률**: 관광지마다 자기 최고 시기를 100으로 둔 상대값. 서로 다른 장소끼리 비교하지 않습니다.
- **FAKE_LLM**: `1`이면 Bedrock을 호출하지 않고 고정 응답을 돌려주는 환경 변수.
- **USE_MOCK**: `1`이면 외부 API 대신 `backend/app/data/`의 샘플·캐시를 쓰는 환경 변수.
- **DEMO_NOW**: 값이 있으면 현재 시각 대신 쓰는 ISO 시각 환경 변수.
- **AWS_REGION**: Bedrock 호출 리전을 정하는 환경 변수(`config.BEDROCK_REGION`으로 읽음) (`ap-northeast-2`).
- **오류 형식**: `docs/api-contract.md`의 `{"error": {"code", "message"}}`.

## Requirements

### Requirement 1: 다국어 응답
**User Story:** 외국인 관광객으로서, 내 언어로 질문하고 내 언어로 답을 받고 싶습니다.

#### Acceptance Criteria

1. 시스템은 `ChatRequest.profile.language`(`en`, `ja`, `zh-Hans`, `zh-Hant`)로 답해야 하고, `ChatResponse.language`에 같은 값을 넣어야 합니다.
2. IF 메시지 언어가 프로필 언어와 다르면 THEN 시스템은 프로필 언어로 답해야 합니다.
3. WHEN 장소를 처음 언급하면 THEN 시스템은 `Place.names[language]` 값을 써야 합니다.
4. IF `Place.names`에 프로필 언어 값이 없거나 빈 문자열이면 THEN 시스템은 다른 언어 값 중 하나로 대체해야 하고, 이를 오류로 처리하지 않아야 합니다.

### Requirement 2: 일정 생성
**User Story:** 여행자로서, 한 문장으로 하루 일정을 받고 싶습니다.

#### Acceptance Criteria

1. WHEN `plan_id`가 `null`이고 사용자가 일정을 요청하면 THEN 시스템은 `backend/app/data/places.json`의 장소 3~5곳으로 새 일정을 만들고 새 `plan_id`를 응답에 넣어야 합니다.
2. 시스템은 장소 선택만 LLM이 하고, 방문 순서와 `start`·`end` 시각은 코드로 계산해야 합니다.
3. WHEN 일정을 만들면 THEN 시스템은 추가된 Stop을 `plan_changes`에 `before: null`인 `StopChange`로 넣어야 합니다.
4. IF 요청에 날짜가 없으면 THEN 시스템은 오늘(`DEMO_NOW`가 있으면 그 날짜)을 쓰고 답변에 날짜를 밝혀야 합니다.
5. 시스템은 생성한 일정에서 서로 다른 Stop의 시간 구간이 겹치지 않게 해야 하고, 각 Stop의 `start`가 `end`보다 앞서야 하며, 두 값 모두 시간대 오프셋을 포함한 ISO 8601 형식이어야 합니다.
6. IF LLM이 고른 `place_id`가 `places.json` 또는 `search_places` 결과에 없으면 THEN 시스템은 그 장소를 제외하고, 한국어 경고 로그를 남기고, 나머지 장소로 일정 생성을 계속해야 합니다.
7. IF 유효한 장소가 0개이면 THEN 시스템은 일정을 만들지 않고, 일정을 만들 수 없다는 사실을 프로필 언어로 알려야 하며, `plan_changes`를 빈 목록으로 돌려줘야 합니다.
8. WHERE `FAKE_LLM=1`이고 `USE_MOCK=1`이면 시스템은 같은 입력에 대해 항상 같은 방문 순서와 같은 `start`·`end`를 만들어야 합니다.

### Requirement 3: 채팅으로 일정 수정
**User Story:** 여행자로서, "여기 너무 붐빌 것 같아" 같은 말로 일정을 고치고 싶습니다.

#### Acceptance Criteria

1. WHEN 사용자가 일정 수정을 요청하면 THEN 시스템은 전체를 다시 만들지 않고 `plan_edit` 도구(`replace_stop`, `add_stop`, `remove_stop`, `move_stop`)로만 고쳐야 합니다.
2. WHEN 수정 이유가 혼잡·비·휴무·빠듯한 이동이면 THEN 시스템은 Guardian의 `propose_repairs` 결과 중 첫 번째 해결안을 써야 합니다.
3. 시스템은 `locked: true`인 Stop을 어떤 경우에도 바꾸지 않아야 합니다. 사용자가 고정 일정 변경을 요청하면 프론트엔드에서 고정을 먼저 풀도록 안내해야 합니다.
4. WHEN 일정이 바뀌면 THEN 시스템은 무엇을 유지했는지 먼저, 무엇을 바꿨는지 다음으로 1~2문장으로 설명하고, 바뀐 내용을 `plan_changes`에 넣어야 합니다.
5. 시스템은 요청 전후로 `locked: true`인 모든 Stop의 `place_id`, `start`, `end`를 같게 유지해야 합니다.
6. 시스템은 실제로 바뀐 Stop만 `plan_changes`에 넣어야 하고, 각 `StopChange.before`는 요청 시작 시점의 Stop과 일치해야 합니다.
7. 시스템은 교체·추가할 `place_id`를 해당 요청에서 `search_places`로 얻은 결과에서만 골라야 합니다. IF 그런 결과가 없으면 THEN 시스템은 변경을 적용하지 않고 바꾸지 못했다는 사실을 프로필 언어로 알려야 합니다.

### Requirement 4: 근거 있는 응답
**User Story:** 여행자로서, 틀린 운영시간이나 지어낸 정보를 받고 싶지 않습니다.

#### Acceptance Criteria

1. 시스템은 장소명·운영시간·요금·이동 시간·혼잡 정도·날씨를 도구 결과에 있는 값으로만 답해야 합니다.
2. IF 도구 결과에 정보가 없으면 THEN 시스템은 모른다고 답하고 확인 방법(직원 문의, 1330 관광통역안내)을 알려야 합니다.
3. 시스템은 서로 다른 장소의 집중률을 비교하지 않아야 합니다. "해운대 평소보다 붐빔"처럼 장소별 평소 대비로 표현해야 합니다.
4. 시스템은 답변에 쓴 도구 결과를 `sources`(`tool`, `id`, `title`)에 넣어야 합니다.
5. 시스템은 `places.json`에 없는 `place_id`를 응답과 `plan_changes`에 넣지 않아야 합니다.
6. 시스템은 `sources`에서 같은 `tool`·`id` 조합을 한 번만, 처음 나온 순서로 넣어야 합니다. 모든 항목은 같은 요청의 도구 결과에 존재해야 하며, 도구를 호출하지 않았으면 `sources`는 빈 목록이어야 합니다.
7. 시스템은 `Source.title`에 프로필 언어 제목을 써야 합니다. IF 프로필 언어 제목이 없으면 THEN 시스템은 다른 언어 제목이나 항목 ID로 대체해 `title`이 비어 있지 않게 해야 합니다. 실패한 도구 호출은 `sources`에 넣지 않아야 합니다.

### Requirement 5: 안전 처리

#### Acceptance Criteria

1. IF 메시지가 부산 여행과 무관하면 THEN 시스템은 정중히 거절하고 여행 주제로 안내해야 합니다.
2. IF 메시지가 지시 변경이나 시스템 프롬프트 공개를 요구하면 THEN 시스템은 거절하고 프롬프트 내용을 드러내지 않아야 합니다.
3. WHEN 식단 질문(할랄·채식·알레르기)을 받으면 THEN 시스템은 데이터에 있는 내용만 답하고 식당에 확인하도록 권해야 합니다.

### Requirement 6: 응답 형식과 성능

#### Acceptance Criteria

1. 시스템은 `/chat` 응답을 스트리밍으로 보내야 하고, 스트림이 끝나면 클라이언트가 `ChatResponse` 하나를 온전히 받을 수 있어야 합니다. 이벤트 형식(`delta`, `done`, `error`)은 `docs/api-contract.md` 「스트리밍」을 따릅니다.
2. 시스템은 도구 호출을 5회 이내로 제한하고 `max_tokens`를 설정해야 합니다.
3. 시스템은 정상 상태에서 15초 이내에 응답해야 합니다.
4. IF 처리 중 오류가 나면 THEN 시스템은 `docs/api-contract.md`의 오류 형식(`{"error": {"code", "message"}}`)으로 답해야 합니다.
5. WHEN 도구 호출 반복이 5회에 도달하면 THEN 시스템은 추가 도구 호출 없이 이미 확보한 결과만으로 `ChatResponse`를 만들어야 합니다.
6. 시스템은 Bedrock 호출과 외부 API 호출마다 타임아웃 5초와 재시도 1회를 적용해야 합니다.
7. IF `AWS_REGION`이 `ap-northeast-2`가 아니면 THEN 시스템은 한국어 오류 로그를 남기고 예외를 발생시켜야 합니다.
8. IF 모델 출력이 `ChatResponse` 검증을 통과하지 못하면 THEN 시스템은 그 출력을 반환하지 않고 오류 형식으로 답해야 하며, 그 요청으로 일정을 바꾸지 않아야 합니다.

### Requirement 7: 개발 모드

#### Acceptance Criteria

1. WHERE `FAKE_LLM=1`이면 시스템은 Bedrock을 호출하지 않고 `ChatResponse` 형식의 고정 응답을 돌려줘야 합니다.
2. WHERE `USE_MOCK=1`이면 도구는 외부 API 대신 `backend/app/data/`의 샘플·캐시를 써야 합니다.
3. IF Bedrock 호출이 제한(throttling)되면 THEN 시스템은 재시도 후에도 실패할 때 오류 형식으로 답해야 합니다.
4. WHERE `FAKE_LLM=1`이고 `USE_MOCK=1`이면 기본 pytest 실행(`bedrock` 마커 제외)의 전체 테스트가 AWS 자격 증명, `DATA_GO_KR_KEY_DECODING`, 네트워크 없이 통과해야 합니다.

### Requirement 8: 평가

#### Acceptance Criteria

1. 시스템은 `backend/eval/`의 평가 질의를 한 번에 실행하는 스크립트를 제공해야 합니다.
2. 목표: 장소 ID 정확도 90% 이상, 언어 일치 100%, 근거 없는 수치 0건, 안전 처리 2/2, 일정 보전 3/3

### Requirement 9: 일정 상태 접근
**User Story:** 여행자로서, 저장된 내 일정을 기준으로 수정되고 다른 사람의 일정과 섞이지 않기를 원합니다.

#### Acceptance Criteria

1. WHEN `plan_id`가 있으면 THEN 시스템은 `app/storage`로 일정을 읽어야 하고, `USE_MOCK=1`이면 `backend/app/data/sample_plan.json`을 읽어야 합니다.
2. IF `plan_id`에 해당하는 일정이 없으면 THEN 시스템은 에이전트를 호출하지 않고 `plan_not_found`(404)로 변환될 수 있는 예외를 발생시켜야 합니다.
3. 시스템은 현재 일정을 요청 범위 컨텍스트로만 도구에 전달해야 하고, 다른 요청과 공유하지 않아야 합니다.
4. 시스템은 `StopChange` 1건마다 저장소에 한 번씩 반영해야 합니다.
5. IF 저장소 반영에 실패하면 THEN 시스템은 성공 응답을 돌려주지 않고 오류 형식으로 답해야 합니다.

### Requirement 10: 로그와 테스트
**User Story:** 개발자로서, 민감한 값 없이 동작을 추적하고 핵심 규칙을 자동 테스트로 확인하고 싶습니다.

#### Acceptance Criteria

1. 시스템은 로그와 주석을 한국어로 작성해야 합니다.
2. 시스템은 키, 사용자 메시지 원문, 프로필 값을 로그에 넣지 않아야 합니다.
3. WHEN Agent 실행이 끝나면 THEN 시스템은 도구 이름별 호출 횟수를 한국어 로그 1건으로 남겨야 하고, 오류로 끝났으면 오류 종류도 그 로그에 포함해야 합니다.
4. 시스템은 임의의 Plan과 변경 요청 100개 이상에 대해 `locked: true`인 Stop이 바뀌지 않음을 property-based test로 검증해야 합니다.
5. 시스템은 임의의 장소 목록 100개 이상에 대해 생성된 Plan이 시간 구간 겹침 없이 모든 `place_id`가 `places.json`에 존재함을 property-based test로 검증해야 합니다.
6. 시스템은 Bedrock 실호출 테스트에 `bedrock` 마커를 붙이고 기본 pytest 실행에서 제외해야 합니다.
7. 시스템은 기존 베이스라인 테스트 11개를 계속 통과해야 합니다.
