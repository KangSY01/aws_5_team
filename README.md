# 부산 외국인 관광객 다국어 맞춤형 안내 에이전트

영어·일본어·중국어 관광객에게 맞춤 일정을 지도 위에 짜 주고, 혼잡·비·휴무·빠듯한 이동을 먼저 찾아 문제 구간만 고쳐 주는 에이전트입니다.

이 저장소는 팀 공용 **뼈대**입니다. 모든 API 경로가 샘플 데이터로 고정 응답을 돌려주며, 기능 로직은 각 담당자가 채웁니다.

- 대회: AWS AI 마에스트로 해커톤 (부산시 지역 현안)
- 제출 마감: 토 08:00 (목표 토 07:00)

## 설치와 실행

[uv](https://docs.astral.sh/uv/)가 필요합니다. Python 3.13은 uv가 알아서 받습니다.

```bash
cd backend
uv sync
uv run pytest -q                        # 테스트
uv run python -m scripts.local_invoke   # handler를 직접 호출해 네 경로 응답 출력
uv run python -m scripts.local_server   # 로컬 서버 http://127.0.0.1:8000 (CORS 허용)
```

스크립트는 반드시 `python -m scripts.이름` 형식으로 `backend/`에서 실행합니다. `python scripts/이름.py`로 실행하면 `app`을 찾지 못합니다.

## 담당 영역

역할 분담 원본은 노션 「역할 분담과 타임테이블」입니다.

| 역할 | 담당 | 맡는 곳 |
|---|---|---|
| A. 에이전트 백엔드 | 노윤지 | `backend/app/agent.py`, `backend/app/tools/plan_edit.py`, `backend/app/storage/`, `backend/app/voice/`(음성 입력 서명 URL), `backend/app/config.py`, `backend/scripts/`, `infra/`(SAM 템플릿·배포 구성) |
| B. 데이터·도구 | 강서영 | `backend/app/data/`, `backend/app/tools/lookup.py`, `backend/app/tools/schedule.py`(일정 시각 계산), `backend/app/speech/`(음성 출력 Polly) |
| C. 프론트엔드 | 이지혜 | `frontend/` (D 폴더 제외) |
| D. 아키텍처 설계 인프라 | 이온규 | `backend/app/guardian/`(예약 점검 로직 `scheduled.py` 포함), `backend/app/prompts.py`, `backend/app/photo/`(사진 인식 백엔드), `backend/eval/`, `frontend/src/features/local-card/`, `frontend/src/features/demo-panel/` |

담당 규칙 세부(테스트 파일, 예약 점검 연결, 계약에 없는 경로)는 [CONTRIBUTING.md](CONTRIBUTING.md)의 「담당 영역」을 따릅니다.

- 지금은 스텁입니다. `agent.py`, `guardian/`, `tools/`의 함수는 시그니처와 docstring, `TODO(담당)`만 있고 호출하면 `NotImplementedError`가 납니다.
- 구현한 뒤에는 `backend/app/handler.py`의 `TODO` 위치에서 고정 응답을 실제 호출로 바꿉니다. 이 파일은 공용 파일이라 아래 규칙을 따릅니다.
- 프론트엔드는 아직 없습니다. 담당자가 Kiro로 생성할 예정입니다.

## 작업 규칙

- **협업 규칙 원본**: 브랜치·커밋·PR·머지 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)에 있습니다.
- **브랜치**: `feat/역할명`에서 작업하고 PR로 `main`에 합칩니다. `main`에 직접 push하지 않습니다.
- **공용 파일**: 아래 파일은 뼈대 담당자 리뷰를 받은 PR로만 수정합니다.
  - `backend/app/models/`
  - `docs/api-contract.md`
  - `backend/app/handler.py`
  - `.kiro/steering/team.md`
- **API 형식**: 요청·응답은 [docs/api-contract.md](docs/api-contract.md)를 따릅니다.
- **키**: `.env`는 커밋하지 않습니다. `backend/.env.example`을 `backend/.env`로 복사해 값을 채우고, `uv run --env-file .env <명령>`으로 실행합니다.
- **Kiro Spec**: 기능은 Kiro Spec으로 만듭니다. Kiro 사용도가 평가에 포함됩니다.
  - 팀 규칙 원본은 `.kiro/steering/team.md`이고 Kiro가 항상 읽습니다.
  - `.kiro/steering/`의 나머지 문서는 제품 개요, 기술 규칙, 구조, 데이터 규칙, API 계약 참조, 프론트엔드 규칙입니다. `team.md`와 다르면 `team.md`를 따릅니다.
  - 기능 스펙은 `.kiro/specs/`(`schedule-guardian`, `chat-agent`)에 있습니다. `tasks.md`의 작업을 순서대로 실행합니다.
  - MCP 서버(AWS 문서, Strands 문서)는 `.kiro/settings/mcp.json`에 설정돼 있습니다.
  - 크레딧 절약: 평소 작업은 Auto 또는 Sonnet, 막히는 문제만 Opus를 씁니다.

## 샘플 데이터

- mock 데이터 원본은 `backend/app/data/`입니다. 프론트엔드 mock은 그 복사본으로 만듭니다.
- **`places.json`의 좌표, 다국어 이름, 가까운 역은 검증하지 않은 값입니다.** 공공데이터로 교체해야 합니다.
- 고정 응답이라 상태가 이어지지 않습니다. `plan-1` 외의 plan_id는 404이고, `PUT /plan`은 저장하지 않고 받은 일정을 그대로 돌려줍니다.

## 일정

원본은 노션 「역할 분담과 타임테이블」입니다.

| 시각 | 목표 |
|---|---|
| 목 23:00 | 점검 0: 뼈대 배포 (화면 → API → Bedrock "Hello", 못 끝내면 금 12:00까지) |
| 금 12:00 | 점검 1: 각자 모듈 단독 동작 시연 |
| 금 18:00 | 점검 2: 전체 연결 (1~2순위, 데모 장면 1·2) |
| 금 21:00 | 점검 3: 3·4·5순위 백엔드 동작 확인 |
| 토 00:00 | 기능 동결 (1~5순위 전부 화면에서 동작) |
| 토 01:30 | 리허설 1 |
| 토 03:00 | 코드 동결, `demo-v1` 태그 |
| 토 06:30 | 리허설 2 |
| 토 07:00 | 제출 |

## 데이터 출처

- 한국관광공사: 관광지 집중률 방문자 추이 예측, 다국어 관광정보서비스, 빅데이터 지역별 방문자수
- 부산광역시: 관광지별 월 방문자, 명소·테마·도보여행 정보
- 기상청: 단기예보
- 부산교통공사: 열차시각표
- 지도: © OpenStreetMap contributors

네이버 블로그 등 웹 게시물은 수집하지 않습니다.

## 제출용 섹션 (토 03:00 이후 작성)

- [ ] 문제 정의와 예상 고객
- [ ] 시스템 구조도 이미지
- [ ] 데모 영상 또는 스크린샷
- [ ] 평가 결과 (장소 ID 정확도, 근거 없는 수치 건수, 응답 시간)
- [ ] 팀원과 역할
- [ ] 확장 계획 (리뷰 광고 필터, 실시간 혼잡 데이터)
