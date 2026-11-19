# Implementation Plan: frontend-plan-list-skeleton

## Overview

`frontend/` 에 React + Vite(JavaScript) 뼈대를 만들고 `GET /plan/plan-1` 결과를 반응형 목록으로 표시한다. 모든 변경은 `frontend/` 안에서만 한다. 공용 파일(`backend/app/models/`, `docs/api-contract.md`, `backend/app/handler.py`, `.kiro/steering/team.md`)은 수정하지 않는다. 코드 주석과 로그는 한국어로 쓴다. `*` 표시 작업은 선택이다.

## Tasks

- [x] 1. React + Vite(JavaScript) 프로젝트 뼈대 만들기
  - `frontend/` 에 Vite React(JavaScript) 템플릿을 구성한다 (`.gitkeep` 은 유지하거나 제거해도 된다).
  - `index.html` 에 `lang="ko"` 와 viewport 메타(`width=device-width, initial-scale=1`)를 `<head>` 안에 정확히 1개 둔다.
  - `.env.example` 에 `VITE_API_BASE_URL=http://127.0.0.1:8000` 을 둔다.
  - Vitest, React Testing Library, jsdom 을 개발 의존성으로 추가하고 `npm test`(`vitest --run`) 스크립트를 만든다.
  - `package.json` 의 `dev`, `build` 스크립트는 `vite`, `vite build` 를 그대로 호출하고 종료 코드나 소스를 가리는 래퍼를 두지 않는다. 소스 파일은 `.js`/`.jsx` 만 쓴다.
  - `frontend/README.md` 에 한국어로 "백엔드 서버 시작"(`uv run python -m scripts.local_server`), "프론트엔드 시작"(`npm install`, `npm run dev`, `npm run build`, `npm test`), "환경 변수 `VITE_API_BASE_URL`"(설명과 기본값) 세 섹션을 각각 분리해 적는다.
  - `frontend/node_modules`, `frontend/dist` 가 저장소 `.gitignore` 로 무시되는지 확인한다. 무시되지 않으면 `frontend/.gitignore` 를 추가한다 (루트 `.gitignore` 는 건드리지 않는다).
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 9.1, 10.3, 10.5_

- [ ] 2. 순수 함수와 상수 구현
  - [ ] 2.1 UI 문구 상수 만들기
    - `src/constants/messages.js` 에 로딩, 빈 상태, 오류 종류별 제목, "다시 시도", "고정", 이름 대체 보조 문구를 한국어로 모은다.
    - _Requirements: 4.6, 6.1, 7.1, 8.1, 8.3, 8.5, 5.3_
  - [x] 2.2 `formatTime` 구현
    - `src/lib/formatTime.js`: ISO 문자열을 `Asia/Seoul` 기준 `HH:mm` 으로 변환한다. `Date.parse` 전에 ISO 8601 형태(`YYYY-MM-DDTHH:mm` 로 시작, 선택적 `Z`/`±HH:mm`)를 먼저 검사한다. 형태 불일치, `NaN`, 비어 있음, 누락, 문자열이 아닌 값은 `--:--` 를 반환하고 예외를 던지지 않는다. 자정이 `24:00` 으로 나오지 않게 하고 `Intl.DateTimeFormat` 은 모듈 수준에서 한 번만 만든다.
    - _Requirements: 5.1, 5.2_
  - [ ]* 2.3 `formatTime` 속성 테스트 작성
    - **Property 4: 시각 형식과 Asia/Seoul 기준**
    - 예시 테스트: `2026-11-21T10:00:00+09:00` → `10:00`, `2026-11-21T01:00:00Z` → `10:00`, 자정 → `00:00`, `abc`/`Nov 5`/빈 문자열/`null`/`undefined` → `--:--`.
    - **Validates: Requirements 5.1, 5.2**
  - [ ] 2.4 `resolvePlaceName` 구현
    - `src/lib/resolvePlaceName.js`: 설계의 결정 순서(지원 언어 → `en` → `names` 의 첫 유효 값 → `place_id`)를 구현한다. 공백만 있는 값은 빈 값으로 취급한다. `names` 가 없거나 객체가 아니어도 예외 없이 동작하고 입력 객체를 변경하지 않는다.
    - `placesById` 는 `places` 를 앞에서부터 순회하며 `place_id` 가 아직 없을 때만 `set` 해, 중복 시 가장 먼저 나온 Place 가 쓰이게 한다.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.7, 4.8, 4.9_
  - [ ]* 2.5 `resolvePlaceName` 속성 테스트 작성
    - **Property 2: 장소명 결정 순서**
    - **Property 3: places 순서 무관**
    - **Property 8: 중복 place_id 는 첫 Place 사용**
    - 예시 테스트: 샘플 4개 장소의 `ja` 이름, `places` 에 없는 `place_id`, `names.ja` 누락, `names` 가 빈 객체, 공백만 있는 이름, `language` 가 `null`/`"JA"`/빈 문자열/알 수 없는 코드.
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.7, 4.8, 4.9**

- [ ] 3. API 클라이언트와 상태 훅 구현
  - [ ] 3.1 `fetchPlan` 과 `PlanClientError` 구현
    - `src/api/planClient.js`: URL 조립(`VITE_API_BASE_URL` 또는 기본값, 끝 `/` 제거), 10초 타임아웃, `network`/`timeout`/`http`/`invalid_response` 분류, Error_Body 해석을 구현한다.
    - 상태가 200 이 아니면(201, 204 등 포함) `http` 오류로 처리한다. Error_Body 는 `error.code`, `error.message` 가 모두 문자열일 때만 `code`/`serverMessage` 에 담는다. 요청은 `GET /plan/{plan_id}` 만 보낸다.
    - _Requirements: 1.5, 1.6, 2.1, 2.2, 2.3, 2.5, 2.6, 8.1, 8.2, 8.4, 8.5, 10.1_
  - [ ]* 3.2 `fetchPlan` 테스트 작성
    - **Property 6: 응답 검증 분류**
    - `fetch` 를 목으로 대체한다. 예시: 200 샘플 응답, 404 `plan_not_found`, 500 비JSON 본문, 200 인데 `stops` 없음, 200 이 아닌 2xx(201, 204), `TypeError`(네트워크), fake timers 로 10초 초과, `VITE_API_BASE_URL` 미설정/빈 문자열일 때 기본 주소.
    - **Validates: Requirements 1.5, 1.6, 2.2, 2.3, 2.6, 8.1, 8.2, 8.4, 8.5**
  - [ ] 3.3 `usePlan` 훅 구현
    - `src/hooks/usePlan.js`: `loading` → `success`/`empty`/`error` 상태, `retry`, 언마운트·재요청 시 `AbortController` 취소, 오류 한국어 콘솔 로그(오류당 1건, 종류와 HTTP 상태(없으면 "없음")만 기록하고 응답 본문 전체·인증 정보·환경 변수 값은 기록하지 않음)를 구현한다.
    - 상태가 `loading` 이면 `retry()` 는 아무것도 하지 않아 동시 요청이 1건을 넘지 않게 한다. `empty`/`error` 에서 재요청 후 `success` 로 가면 이전 화면은 상태 전환만으로 교체된다. StrictMode 이중 마운트에서도 최종 상태가 같아야 한다.
    - _Requirements: 2.1, 2.4, 6.3, 6.4, 6.5, 6.6, 7.1, 7.5, 8.7, 8.10_

- [ ] 4. 체크포인트 - 순수 로직 확인
  - `npm test` 를 실행해 지금까지의 테스트가 통과하는지 확인한다. 문제가 있으면 사용자에게 묻는다.

- [ ] 5. 화면 컴포넌트와 스타일 구현
  - [ ] 5.1 샘플 mock 복사
    - `backend/app/data/sample_plan.json`, `places.json` 을 `frontend/src/mocks/` 로 복사한다 (원본은 수정하지 않는다). 복사 사실과 동기화 규칙을 `frontend/README.md` 에 적는다.
    - _Requirements: 10.4_
  - [ ] 5.2 `StopItem` 구현
    - `src/components/StopItem.jsx`: `<time dateTime>` 으로 감싼 `{start} – {end}`(공백, en dash, 공백), 장소명(Display_Language 에 맞는 `lang` 속성, `place_id` 로 대체되면 `lang` 없음, 텍스트로만 출력하고 `dangerouslySetInnerHTML` 금지), `locked === true` 일 때만 SVG 잠금 아이콘(`aria-hidden`) + "고정" 텍스트, 이름이 `place_id` 로 대체될 때만 같은 줄에 보조 문구를 표시한다. 한쪽 시각이 `--:--` 여도 나머지는 정상 표시한다.
    - _Requirements: 4.6, 4.7, 4.10, 5.1, 5.2, 5.3, 5.4, 5.5_
  - [ ] 5.3 `PlanList` 구현
    - `src/components/PlanList.jsx`: `plan.date` 를 변환 없이 그대로 제목으로 표시, `places` 를 `Map` 으로 인덱싱(중복 `place_id` 는 첫 Place), `<ol>` 에 `plan.stops` 순서대로 `StopItem` 렌더링.
    - React `key` 는 `stop_id` 이되 중복이면 등장 순번을 붙여(`s1`, `s1#2`, ...) 고유하게 만든다. 중복이어도 모든 원소를 순서대로 표시하고 오류는 표시하지 않는다.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 4.7, 4.8, 4.9_
  - [ ] 5.4 `LoadingState`, `EmptyState`, `ErrorState` 구현
    - `LoadingState`: `role="status"`, `aria-busy="true"`, "일정을 불러오는 중" 문구. 로딩이 끝나면 컴포넌트가 사라져 문구와 `aria-busy` 가 함께 제거되고, 로딩 화면에는 "다시 시도" 버튼이 없다.
    - `EmptyState`: "아직 일정이 없습니다" 1회와 `plan.date`. `date` 가 없거나 빈 문자열이면 날짜 영역을 렌더링하지 않는다.
    - `ErrorState`: `role="alert"`, 설계의 오류 종류별 표 문구(`network`, `timeout`, 404 `plan_not_found`, Error_Body 있음/없음(`HTTP {status}`), `invalid_response`), 네트워크 오류 시 Base_URL 전체 표시, 활성 "다시 시도" 버튼. 서버 `message` 는 텍스트 노드로만 출력한다.
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 7.1, 7.2, 7.3, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.8, 8.9_
  - [ ] 5.5 `App` 연결과 반응형 스타일
    - `src/App.jsx` 에서 `usePlan()` 상태에 따라 정확히 하나의 화면을 렌더링한다. `src/main.jsx` 에서 마운트한다.
    - `src/styles/app.css`: 모바일(360~480px) 기본 스타일(좌우 여백 16px, 카드, 시각 범위 별도 줄), `@media (min-width: 481px)` 태블릿 한 열·좌우 여백 32px, `@media (min-width: 1024px)` `max-width: 760px`·`margin-inline: auto` 가운데 정렬과 2열 항목(시각 열 8rem 고정), `overflow-wrap: anywhere`, 버튼 `min-height: 44px; min-width: 44px`, CJK 포함 글꼴 목록, 본문 `#1f2933`/보조 `#52606d` on `#ffffff`(대비 4.5:1 이상).
    - 360px 미만에서는 `overflow-x: hidden` 을 쓰지 않고 `body { min-width: 0 }`, 항목 `min-width: 320px` 로 가로 스크롤을 허용해 내용이 잘리지 않게 한다.
    - _Requirements: 6.3, 7.3, 8.7, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10_
  - [ ]* 5.6 컴포넌트 테스트 작성
    - **Property 1: 순서와 개수 보존** (`place_id`·`stop_id` 중복, `start` 뒤섞임, 임의 `plan.date` 포함)
    - **Property 4 (StopItem 부분): 한쪽 시각이 해석 불가여도 다른 시각·장소명·고정 표시는 정상**
    - **Property 5: 고정 표시는 locked 와 일치**
    - **Property 7: 상태 화면 배타성** (오류에는 `role="alert"` + 활성 버튼, 로딩에는 버튼 없음)
    - 예시: `mocks/` 샘플을 렌더링해 `ja` 이름 4개와 `10:00 – 11:30` 등 시각 범위 확인, 자갈치시장만 "고정", 오류 후 "다시 시도" 로 목록 복구, 로딩 중 "다시 시도" 버튼 없음과 재요청 1건(`fetch` 목 사용), `empty` 에서 재요청 후 항목이 있으면 빈 상태 문구 제거.
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.7, 5.2, 5.3, 5.4, 5.6, 6.3, 6.5, 7.5, 8.6, 8.8, 8.9**
  - [ ]* 5.7 장소명 표시 속성 테스트 작성
    - **Property 9: 장소명 텍스트 표시와 대체 문구**
    - `<`, `>`, `&`, 따옴표를 포함한 임의 문자열이 DOM 텍스트와 정확히 같고 HTML 요소가 새로 생기지 않는지, 대체 보조 문구가 `isFallbackToId` 가 `true` 일 때에 한정해 표시되는지 확인한다.
    - **Validates: Requirements 4.6, 4.7, 4.10**
  - [ ]* 5.8 빈 일정 화면 속성 테스트 작성
    - **Property 10: 빈 일정 화면**
    - 임의 `plan.date`(빈 문자열·누락 포함)에서 `stops: []` 일 때 "아직 일정이 없습니다" 가 정확히 1회, Stop_Item 과 오류 표시 0개, 날짜 영역은 `date` 가 비어 있지 않을 때에 한정해 표시되는지 확인한다.
    - **Validates: Requirements 3.6, 7.1, 7.2, 7.3, 7.4**

- [ ] 6. 최종 체크포인트 - 빌드와 수동 검증
  - `npm test`, `npm run build` 가 통과하는지 확인한다.
  - 백엔드(`uv run python -m scripts.local_server`)와 프론트엔드(`npm run dev`)를 띄우고 `design.md` 의 수동 검증 절차 M1~M20 을 확인한다.
    - 반응형: M1~M5(360/390/480/481/768/1023/1024/1280/1920px), M14(360px 미만 가로 스크롤), M15(40자 이상 장소명), M16(터치 44px, 대비 4.5:1, CJK 글꼴)
    - 표시·상태: M6(고정 표시), M7(로딩), M8(서버 중지 오류), M9(404), M10(빈 일정), M11(키보드), M12(재시도 후 로딩·버튼 없음·동시 요청 1건), M13(10초 시간 초과)
    - 범위·설정: M17(`npm install`/`dev`/`build`, Base_URL 기본값·지정값), M18(viewport 메타 1개, `.ts`/`.tsx` 0개, README 세 섹션), M19(`GET /plan/plan-1` 만 요청, MapLibre 0개), M20(`git diff --name-only` 경로, 공용 파일·`backend/app/data/` diff 0줄)
  - `git status` 로 `frontend/` 와 `.kiro/specs/frontend-plan-list-skeleton/` 밖의 변경이 없는지, 공용 파일이 수정되지 않았는지 확인한다.
  - 공용 파일 변경이 필요해 보이는 사항이 새로 생겼으면 `design.md` 의 "팀원 검토 필요 항목" 에 추가하고 사용자에게 알린다.
  - _Requirements: 1.2, 1.3, 1.5, 1.6, 1.8, 2.1, 2.2, 2.5, 5.6, 6.1, 6.4, 6.5, 6.6, 7.1, 8.1, 8.3, 8.5, 8.7, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.4", "3.1", "5.1"] },
    { "id": 2, "tasks": ["2.3", "2.5", "3.2", "3.3", "5.2"] },
    { "id": 3, "tasks": ["5.3", "5.4"] },
    { "id": 4, "tasks": ["5.5"] },
    { "id": 5, "tasks": ["5.6", "5.7", "5.8"] }
  ]
}
```

## Notes

- 후속 작업(지도, Guardian, 채팅, 일정 저장, 다국어 UI, 자동 반응형 테스트, 배포)은 `design.md` 의 "후속 작업" 절에 있다.
- 공용 파일 관련 질문은 `design.md` 의 "팀원 검토 필요 항목" R1~R9 에 있다.
- 속성 테스트(fast-check)를 쓰려면 개발 의존성으로 `fast-check` 를 추가한다.
