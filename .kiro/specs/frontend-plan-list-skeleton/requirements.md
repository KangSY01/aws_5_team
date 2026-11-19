# Requirements Document

## Introduction

프론트엔드 첫 뼈대 기능이다. `frontend/` 에 React + Vite(JavaScript) 프로젝트를 만들고, 로컬 백엔드(`uv run python -m scripts.local_server`, `http://127.0.0.1:8000`)의 `GET /plan/plan-1` 을 호출해 샘플 일정(plan.stops)을 반응형 목록으로 보여 준다.

이 기능은 목록 표시까지만 다룬다. 지도(MapLibre), Schedule Guardian(`POST /plan/check`), 채팅(`POST /chat`), 일정 저장(`PUT /plan/{plan_id}`)은 후속 작업이며 `design.md` 의 "후속 작업" 절에 기록한다.

공용 파일(`backend/app/models/`, `docs/api-contract.md`, `backend/app/handler.py`, `.kiro/steering/team.md`)은 수정하지 않는다. 변경이 필요해 보이는 사항은 `design.md` 의 "팀원 검토 필요 항목" 에만 기록한다.

## Glossary

- **Frontend_App**: `frontend/` 에 만드는 React + Vite(JavaScript) 웹 애플리케이션.
- **Frontend_App 개발자**: 이번 기능의 변경 사항을 작성하고 커밋하는 사람.
- **Plan_API**: `GET http://127.0.0.1:8000/plan/{plan_id}` 엔드포인트. `docs/api-contract.md` 의 "GET /plan/{plan_id}" 를 따른다.
- **Base_URL**: Plan_API 요청에 사용하는 기준 주소. 환경 변수 `VITE_API_BASE_URL` 값 또는 기본값 `http://127.0.0.1:8000`.
- **Plan_Client**: Frontend_App 안에서 Plan_API 를 호출하고 응답을 해석하는 모듈.
- **Plan_List**: 일정의 stop 을 순서대로 보여 주는 화면 영역.
- **Stop_Item**: Plan_List 안에서 stop 하나를 나타내는 항목.
- **Plan**: Plan_API 응답의 `plan` 객체 (`plan_id`, `date`, `profile`, `stops`).
- **Stop**: `plan.stops` 의 원소 (`stop_id`, `place_id`, `start`, `end`, `locked`).
- **Place**: Plan_API 응답의 `places` 배열 원소 (`place_id`, `names`, ...).
- **Place_Name_Resolver**: Stop 의 `place_id` 로 Place 를 찾아 표시할 장소명을 결정하는 함수.
- **Display_Language**: `plan.profile.language` 값. `en`, `ja`, `zh-Hans`, `zh-Hant` 중 하나.
- **Error_Body**: `{ "error": { "code": string, "message": string } }` 형식의 오류 응답 본문. `error` 객체 안에 문자열 `code` 와 문자열 `message` 를 모두 포함한다.
- **Mobile_Viewport**: 너비 360px 이상 480px 이하의 화면 (검증 기준 360px, 390px).
- **Tablet_Viewport**: 너비 481px 이상 1023px 이하의 화면 (검증 기준 768px).
- **Desktop_Viewport**: 너비 1024px 이상 1920px 이하의 화면 (검증 기준 1280px, 1920px).
- **Local_Backend**: `backend/` 에서 `uv run python -m scripts.local_server` 로 띄운 개발용 서버. CORS 를 전부 허용한다.

## Requirements

### Requirement 1: 프로젝트 뼈대

**User Story:** As a 프론트엔드 개발자, I want `frontend/` 에 React + Vite(JavaScript) 프로젝트 뼈대가 있기를, so that 팀원이 같은 방법으로 실행하고 이어서 개발할 수 있다.

#### Acceptance Criteria

1. THE Frontend_App SHALL React 와 Vite 로 구성되고, 모든 애플리케이션 소스 파일을 JavaScript(`.js` 또는 `.jsx`)로 작성하며 TypeScript 파일(`.ts`, `.tsx`)을 포함하지 않는다.
2. WHEN 개발자가 `frontend/` 에서 `npm install` 을 실행하고 이어서 `npm run dev` 를 실행하면, THE Frontend_App SHALL 명령 실행 후 10초 이내에 개발 서버를 시작하고, 출력된 로컬 주소를 브라우저에서 열었을 때 첫 화면을 표시하며 브라우저 콘솔에 오류가 없어야 한다.
3. WHEN 개발자가 `frontend/` 에서 `npm run build` 를 실행하면, THE Frontend_App SHALL 종료 코드 0 으로 완료하고 정적 산출물을 생성한다.
4. IF `npm install`, `npm run dev`, 또는 `npm run build` 가 실패하면, THEN THE Frontend_App SHALL 0이 아닌 종료 코드와 원인을 나타내는 오류 출력을 터미널에 표시하고, `frontend/` 의 기존 소스 파일을 변경하지 않는다.
5. WHEN Frontend_App 이 Plan_API 의 Base_URL 을 결정할 때, IF 환경 변수 `VITE_API_BASE_URL` 에 비어 있지 않은 값이 설정되어 있으면, THEN THE Frontend_App SHALL 해당 값을 Base_URL 로 사용한다.
6. WHEN Frontend_App 이 Plan_API 의 Base_URL 을 결정할 때, IF 환경 변수 `VITE_API_BASE_URL` 이 설정되지 않았거나 빈 문자열이면, THEN THE Frontend_App SHALL `http://127.0.0.1:8000` 을 Base_URL 로 사용한다.
7. THE Frontend_App SHALL 코드 주석과 로그 메시지를 한국어로 작성한다. 단, 고유 명칭, 코드 식별자, 명령어는 영문을 허용한다.
8. THE Frontend_App SHALL `frontend/README.md` 에 한국어로 다음 세 항목을 각각 별도 섹션으로 기록한다: 백엔드 서버 시작 방법, 프론트엔드 시작 방법(`npm install` 및 `npm run dev` 명령 포함), 환경 변수 `VITE_API_BASE_URL` 의 설명과 기본값.

### Requirement 2: 일정 불러오기

**User Story:** As a 사용자, I want 앱을 열면 샘플 일정을 자동으로 불러오기를, so that 별도 조작 없이 일정을 볼 수 있다.

#### Acceptance Criteria

1. WHEN Frontend_App 의 첫 화면이 열리면, THE Plan_Client SHALL `GET {Base_URL}/plan/plan-1` 을 1회 요청하고, THE Frontend_App SHALL 응답을 기다리는 동안 로딩 표시를 보여 준다.
2. WHEN Plan_API 가 HTTP 200 과 `plan`, `places` 를 가진 JSON 을 반환하면, THE Frontend_App SHALL 응답 수신 후 1초 이내에 `plan.stops` 배열의 모든 항목을 배열 순서대로 Plan_List 에 표시하고 로딩 표시를 제거한다.
3. IF HTTP 200 응답 본문이 JSON 이 아니거나 `plan.stops` 배열 또는 `places` 배열이 없으면, THEN THE Plan_Client SHALL 응답 형식 오류로 처리하고, THE Frontend_App SHALL 응답 형식 오류를 알리는 메시지와 "다시 시도" 버튼을 가진 오류 화면을 표시하며 Plan_List 를 표시하지 않는다.
4. WHEN 사용자가 오류 화면의 "다시 시도" 버튼을 누르면, THE Plan_Client SHALL 최초 요청과 같은 `GET {Base_URL}/plan/plan-1` 요청을 1회 다시 보내고, THE Frontend_App SHALL 오류 화면을 로딩 표시로 바꾼다.
5. IF 요청 후 10초 안에 응답이 오지 않으면, THEN THE Plan_Client SHALL 요청을 취소하고 시간 초과 오류로 처리하며, THE Frontend_App SHALL 시간 초과를 알리는 메시지와 "다시 시도" 버튼을 가진 오류 화면을 표시한다.
6. IF Plan_API 가 HTTP 200 이 아닌 상태 코드를 반환하거나 네트워크 연결에 실패하면, THEN THE Plan_Client SHALL 요청 실패 오류로 처리하고, THE Frontend_App SHALL 요청 실패를 알리는 메시지와 "다시 시도" 버튼을 가진 오류 화면을 표시하며 Plan_List 를 표시하지 않는다.

### Requirement 3: 일정 순서 표시

**User Story:** As a 사용자, I want 일정이 서버가 준 순서 그대로 보이기를, so that 하루 동선을 올바른 순서로 이해할 수 있다.

#### Acceptance Criteria

1. WHEN Plan_List 가 `plan` 을 수신하면, THE Plan_List SHALL `plan.stops` 배열의 인덱스 오름차순(0번째 원소가 첫 번째 위치)으로 Stop_Item 을 표시하고, `start` 등 다른 필드를 기준으로 재정렬하지 않는다.
2. WHEN Plan_List 가 `plan` 을 수신하면, THE Plan_List SHALL `plan.stops` 의 원소 하나당 Stop_Item 을 정확히 하나 표시하여, 표시된 Stop_Item 수가 `plan.stops.length` 와 같도록 한다.
3. WHEN 두 개 이상의 Stop 이 같은 `place_id` 를 가지면, THE Plan_List SHALL 각 Stop 을 서로 다른 Stop_Item 으로 표시하고 병합하거나 생략하지 않는다.
4. THE Plan_List SHALL 각 Stop_Item 의 고유 식별자로 `stop_id` 를 사용하고, `place_id` 나 배열 인덱스를 식별자로 사용하지 않는다.
5. WHEN Plan_List 가 `plan` 을 수신하면, THE Plan_List SHALL Stop_Item 목록 위에 `plan.date` 값을 `YYYY-MM-DD` 형식 그대로(변환, 현지화, 시간대 보정 없이) 표시한다.
6. IF `plan.stops` 가 빈 배열이면, THEN THE Plan_List SHALL Stop_Item 을 0개 표시하고, `plan.date` 는 계속 표시하며, 일정이 비어 있음을 알리는 안내 문구를 표시한다.
7. IF `plan.stops` 에 `stop_id` 가 중복된 원소가 둘 이상 있으면, THEN THE Plan_List SHALL 중복된 원소도 모두 `plan.stops` 순서대로 표시하고, 오류 표시 없이 렌더링을 계속한다.

### Requirement 4: 장소명 표시

**User Story:** As a 외국인 관광객, I want 장소 이름이 내 언어로 보이기를, so that 어떤 곳인지 바로 알 수 있다.

#### Acceptance Criteria

1. WHEN Stop 의 `place_id` 와 같은 `place_id` 를 가진 Place 가 `places` 에 있고 `names[Display_Language]` 가 공백 문자만으로 이루어지지 않은 1자 이상의 문자열이면, THE Place_Name_Resolver SHALL `names[Display_Language]` 를 장소명으로 반환한다.
2. IF Place 는 있으나 `names[Display_Language]` 가 없거나, 빈 문자열이거나, 공백 문자만으로 이루어져 있으면, THEN THE Place_Name_Resolver SHALL `names.en` 을 장소명으로 반환한다.
3. IF Place 는 있으나 `names[Display_Language]` 와 `names.en` 이 모두 없거나, 빈 문자열이거나, 공백 문자만으로 이루어져 있으면, THEN THE Place_Name_Resolver SHALL `names` 객체의 키 순서상 공백 문자만으로 이루어지지 않은 1자 이상의 문자열인 첫 번째 값을 장소명으로 반환한다.
4. IF `places` 에 Stop 의 `place_id` 와 같은 Place 가 없거나 Place 의 `names` 에 공백 문자만으로 이루어지지 않은 1자 이상의 문자열 값이 없으면, THEN THE Place_Name_Resolver SHALL `place_id` 문자열을 장소명으로 반환한다.
5. IF `plan.profile.language` 가 `en`, `ja`, `zh-Hans`, `zh-Hant` 중 하나가 아니거나(대소문자 구분, 값이 null 이거나 필드가 없는 경우 포함) 빈 문자열이면, THEN THE Place_Name_Resolver SHALL `en` 을 Display_Language 로 사용한다.
6. WHEN 장소명이 `place_id` 로 대체되면, THE Stop_Item SHALL 대체 사실을 알리는 보조 문구를 장소명과 같은 줄에 표시한다.
7. WHEN 장소명이 `place_id` 로 대체되지 않으면, THE Stop_Item SHALL 대체 사실을 알리는 보조 문구를 표시하지 않는다.
8. THE Place_Name_Resolver SHALL `places` 배열의 순서와 관계없이 `place_id` 로 Place 를 찾는다.
9. IF `places` 에 같은 `place_id` 를 가진 Place 가 둘 이상 있으면, THEN THE Place_Name_Resolver SHALL `places` 배열에서 가장 먼저 나오는 Place 를 사용한다.
10. THE Frontend_App SHALL `names` 에서 읽은 문자열을 HTML 로 해석하지 않고 텍스트로 표시한다. 이때 `<`, `>`, `&` 등 HTML 특수 문자는 입력된 문자 그대로 화면에 표시된다.

### Requirement 5: 시각과 고정 상태 표시

**User Story:** As a 사용자, I want 각 일정의 시작·종료 시각과 고정 여부가 보이기를, so that 언제 어디에 있어야 하는지, 어떤 일정이 고정인지 알 수 있다.

#### Acceptance Criteria

1. WHEN Stop_Item 이 렌더링되면, THE Stop_Item SHALL `start` 와 `end` 를 각각 `Asia/Seoul` 시간대의 24시간제 `HH:mm` 형식(시 2자리, 분 2자리, 00:00 ~ 23:59)으로 표시한다 (예: `2026-11-21T10:00:00+09:00` 은 `10:00`, `2026-11-21T01:00:00Z` 는 `10:00`).
2. IF `start` 또는 `end` 가 ISO 8601 날짜·시각 형식으로 해석할 수 없는 값이거나 비어 있거나 누락되었으면, THEN THE Stop_Item SHALL 해당 시각만 `--:--` 로 표시하고, 다른 시각 값과 장소명, 고정 표시를 포함한 나머지 항목은 정상 표시하며, 오류 화면이나 예외로 목록 렌더링을 중단하지 않는다.
3. WHILE Stop 의 `locked` 가 `true` 이면, THE Stop_Item SHALL 색상과 별개로 "고정" 이라는 텍스트와 잠금 아이콘을 둘 다 해당 Stop_Item 안에 표시한다.
4. WHILE Stop 의 `locked` 가 `false` 이거나 누락되었으면, THE Stop_Item SHALL "고정" 텍스트와 잠금 아이콘을 모두 표시하지 않는다.
5. WHEN Stop_Item 이 렌더링되면, THE Stop_Item SHALL 시각 범위를 `{start} – {end}` 형태(시작 시각, 공백, en dash `–`, 공백, 종료 시각)로 장소명과 같은 Stop_Item 안에 표시한다.
6. WHERE 샘플 일정(`plan-1`)을 불러온 경우, THE Plan_List SHALL 4개의 Stop_Item 을 다음 순서로 `ja` 이름과 함께 표시하고, `locked` 가 `true` 인 자갈치시장 Stop_Item 에만 고정 표시를 나타낸다: `10:00 – 11:30` 감천문화마을, `12:00 – 13:00` 자갈치시장(고정), `13:30 – 14:30` 부산타워, `15:30 – 17:00` 해운대해수욕장. (장소명은 places.json 의 ja 값을 그대로 쓴다.)

### Requirement 6: 로딩 상태

**User Story:** As a 사용자, I want 불러오는 동안 진행 중임을 알 수 있기를, so that 화면이 멈춘 것으로 오해하지 않는다.

#### Acceptance Criteria

1. WHEN Plan_API 요청이 전송되면, THE Frontend_App SHALL 요청 전송 후 100ms 이내에 로딩 표시와 "일정을 불러오는 중" 문구를 화면에 표시한다.
2. WHILE Plan_API 응답을 기다리는 중이면, THE Frontend_App SHALL 로딩 영역에 `role="status"` 와 `aria-busy="true"` 를 설정하고 "일정을 불러오는 중" 문구를 로딩 영역 안에 유지한다.
3. WHEN Plan_API 응답 처리가 성공, 빈 일정, 오류 중 하나로 끝나면, THE Frontend_App SHALL 100ms 이내에 로딩 표시와 "일정을 불러오는 중" 문구를 화면에서 제거하고 `aria-busy` 를 `"false"` 로 설정하거나 속성을 제거한다.
4. WHEN 사용자가 "다시 시도" 를 눌러 재요청이 시작되면, THE Frontend_App SHALL 이전 오류 화면을 제거하고 100ms 이내에 로딩 표시를 보여 준다.
5. WHILE Plan_API 응답을 기다리는 중이면, THE Frontend_App SHALL "다시 시도" 버튼을 비활성화하거나 숨겨서 중복 요청이 동시에 1건을 초과하지 않도록 한다.
6. IF Plan_API 응답이 요청 후 10초 안에 도착하지 않으면, THEN THE Frontend_App SHALL 요청을 종료하고 로딩 표시를 제거한 뒤 오류 화면을 표시한다.

### Requirement 7: 빈 일정 상태

**User Story:** As a 사용자, I want 일정이 비어 있을 때 안내를 보기를, so that 오류와 빈 일정을 구분할 수 있다.

#### Acceptance Criteria

1. WHEN Plan_API 가 HTTP 200 으로 `plan.stops` 가 빈 배열(`[]`)인 응답을 반환하면, THE Frontend_App SHALL 응답 수신 후 1초 이내에 "아직 일정이 없습니다" 라는 빈 상태 문구를 화면에 정확히 1회 표시한다.
2. WHILE 빈 상태 문구가 표시 중이면, THE Frontend_App SHALL 응답의 `plan.date` 값을 빈 상태 문구와 같은 화면에 함께 표시한다.
3. WHILE 빈 상태 문구가 표시 중이면, THE Frontend_App SHALL 오류 표시와 Stop_Item 을 0개로 유지한다.
4. IF Plan_API 가 HTTP 200 으로 `plan.stops` 가 빈 배열인 응답을 반환했으나 `plan.date` 가 존재하지 않거나 빈 문자열이면, THEN THE Frontend_App SHALL 빈 상태 문구만 표시하고 `plan.date` 영역은 표시하지 않으며 오류 표시도 하지 않는다.
5. WHEN 빈 상태 문구가 표시 중인 상태에서 Plan_API 가 `plan.stops` 에 1개 이상의 항목이 있는 HTTP 200 응답을 반환하면, THE Frontend_App SHALL 빈 상태 문구를 제거하고 항목 수만큼 Stop_Item 을 표시한다.

### Requirement 8: 요청 오류 상태

**User Story:** As a 사용자, I want 요청이 실패했을 때 원인을 알 수 있기를, so that 다시 시도하거나 문제를 전달할 수 있다.

#### Acceptance Criteria

1. IF 네트워크 오류(서버 미실행, 연결 거부, CORS 차단)로 요청이 실패하면, THEN THE Frontend_App SHALL "서버에 연결할 수 없습니다" 문구와 요청에 사용한 Base_URL 전체 문자열을 오류 영역에 표시한다.
2. IF Plan_API 가 HTTP 400~499 또는 500~599 상태와 Error_Body 를 반환하면, THEN THE Frontend_App SHALL Error_Body 의 `code` 와 `message` 값을 오류 영역에 그대로 표시한다.
3. IF Plan_API 가 HTTP 404 와 `code` 가 `plan_not_found` 인 Error_Body 를 반환하면, THEN THE Frontend_App SHALL "일정을 찾을 수 없습니다" 문구와 Error_Body 의 `message` 를 표시한다.
4. IF Plan_API 가 HTTP 400~499 또는 500~599 상태를 반환했지만 본문이 Error_Body 형식(`error` 객체 안에 문자열 `code` 와 문자열 `message` 를 모두 포함하는 JSON 객체)이 아니면, THEN THE Frontend_App SHALL 해당 HTTP 상태 코드 숫자를 포함한 일반 오류 문구를 표시한다.
5. IF 요청 시작 후 10초 안에 응답이 완료되지 않으면, THEN THE Frontend_App SHALL 요청을 중단하고 "응답이 지연되고 있습니다" 문구를 오류 영역에 표시한다.
6. WHILE 오류 화면이 표시 중이면, THE Frontend_App SHALL 활성화된 "다시 시도" 버튼을 제공한다.
7. WHEN 사용자가 "다시 시도" 버튼을 누르면, THE Frontend_App SHALL 실패한 요청과 동일한 요청을 1회 다시 전송하고 오류 영역을 제거한다.
8. WHILE 오류 화면이 표시 중이면, THE Frontend_App SHALL Plan_List 와 빈 상태 문구를 표시하지 않는다.
9. WHILE 오류 화면이 표시 중이면, THE Frontend_App SHALL 오류 영역에 `role="alert"` 속성을 설정하여 보조 기술이 즉시 알리도록 한다.
10. IF 요청 처리 중 오류가 발생하면, THEN THE Frontend_App SHALL 오류 종류와 HTTP 상태(없으면 "없음")를 포함한 한국어 로그 1건을 콘솔에 남기고, 인증 정보와 환경 변수 값은 로그에 포함하지 않는다.

### Requirement 9: 반응형 레이아웃

**User Story:** As a 사용자, I want 휴대폰과 데스크톱 모두에서 일정이 읽기 쉽게 보이기를, so that 어떤 기기에서도 일정을 확인할 수 있다.

#### Acceptance Criteria

1. THE Frontend_App SHALL `<meta name="viewport" content="width=device-width, initial-scale=1">` 를 HTML 문서의 `<head>` 안에 정확히 한 번 포함한다.
2. WHILE 화면 너비가 Mobile_Viewport(360px 이상 480px 이하)이면, THE Plan_List SHALL Stop_Item 을 한 열로 쌓아 표시하고, 각 Stop_Item 의 시각 범위를 장소명 위 또는 아래의 별도 줄에 표시한다.
3. WHILE 화면 너비가 360px 이상 1920px 이하이면, THE Frontend_App SHALL 문서의 `scrollWidth` 를 `clientWidth` 이하로 유지하여 가로 스크롤을 만들지 않는다.
4. WHILE 화면 너비가 Tablet_Viewport(481px 이상 1023px 이하)이면, THE Plan_List SHALL Stop_Item 을 한 열로 표시하고, 콘텐츠 영역의 좌우 여백을 각각 Mobile_Viewport 의 좌우 여백보다 8px 이상 크게 둔다.
5. WHILE 화면 너비가 Desktop_Viewport(1024px 이상 1920px 이하)이면, THE Plan_List SHALL 최대 너비 760px 의 콘텐츠 영역을 화면 가로 중앙에 두고(좌우 여백 차이 1px 이하), 각 Stop_Item 의 시각 범위를 장소명의 왼쪽 열에 표시한다.
6. WHILE Stop_Item 의 장소명이 40자 이상이면, THE Stop_Item SHALL 장소명 전체를 줄바꿈하여 표시하고, 장소명이 Stop_Item 의 경계 밖으로 넘치거나 잘리지 않게 한다.
7. THE Frontend_App SHALL "다시 시도" 버튼 등 터치로 누르는 모든 요소의 높이와 너비를 각각 44px 이상으로 한다.
8. THE Frontend_App SHALL 본문 텍스트와 배경의 명도 대비를 WCAG 2.1 AA 기준인 4.5:1 이상으로 한다.
9. THE Frontend_App SHALL 일본어, 중국어 간체, 중국어 번체 문자가 대체 글리프(두부 문자, □) 없이 표시되도록 CJK 글꼴을 포함한 시스템 글꼴 목록을 지정한다.
10. IF 화면 너비가 360px 미만이면, THEN THE Frontend_App SHALL 콘텐츠를 잘라 숨기지 않고 가로 스크롤을 허용하여 모든 Stop_Item 내용에 접근할 수 있게 한다.

### Requirement 10: 작업 범위

**User Story:** As a 팀원, I want 이번 작업 범위가 명확하기를, so that 공용 파일 충돌이나 다른 담당자의 작업 침범이 없다.

#### Acceptance Criteria

1. THE Frontend_App SHALL 이번 기능의 실행 중 네트워크 요청으로 `GET /plan/{plan_id}` 만 전송하고, `POST /plan/check`, `POST /chat`, `PUT /plan/{plan_id}` 요청은 0건 전송한다.
2. THE Frontend_App SHALL 이번 기능의 화면과 소스 코드에 지도(MapLibre) 화면, MapLibre 컴포넌트, MapLibre 패키지 의존성을 0개 포함한다.
3. WHEN 이번 기능의 변경 사항이 커밋되기 전에 `git diff --name-only` 로 확인되면, THE Frontend_App 개발자 SHALL 변경된 모든 파일의 경로가 `frontend/` 또는 `.kiro/specs/frontend-plan-list-skeleton/` 로 시작하도록 한다.
4. WHERE 테스트나 개발용 mock 이 필요한 경우, THE Frontend_App SHALL `backend/app/data/` 의 샘플 파일을 `frontend/` 안으로 복사한 사본만 사용하고, `backend/app/data/` 의 파일 내용은 변경하지 않는다.
5. THE Frontend_App 개발자 SHALL 공용 파일(`backend/app/models/` 하위 모든 파일, `docs/api-contract.md`, `backend/app/handler.py`, `.kiro/steering/team.md`)의 내용을 변경하지 않아, 해당 경로의 `git diff` 결과가 0줄이다.
6. IF 공용 파일 변경이 필요해 보이는 사항이 발견되면, THEN THE Frontend_App 개발자 SHALL 해당 파일 경로, 변경이 필요해 보이는 이유, 제안 내용을 `design.md` 의 "팀원 검토 필요 항목" 섹션에 항목당 1건씩 기록하고 해당 공용 파일은 수정하지 않는다.
