# 협업 규칙

브랜치, 커밋, PR, 머지 규칙의 원본 문서입니다. `README.md`와 `.kiro/steering/structure.md`는 이 문서를 요약합니다. 규칙을 바꾸려면 이 문서를 고치고 팀에 공유하십시오.
팀 규칙 전체의 원본은 `.kiro/steering/team.md`입니다. 두 문서가 다르면 `team.md`를 따릅니다.

## 원칙
- `main`은 언제든 데모 가능한 상태로 유지합니다.
- 자기 담당 영역 안에서 작업합니다. 공용 파일은 뼈대 담당자 리뷰를 거친 PR로만 바꿉니다.
- PR은 작게, 자주 머지합니다. 브랜치는 수 시간 안에 머지합니다.

## 담당 영역
역할 분담 원본은 노션 「역할 분담과 타임테이블」입니다.

| 역할 | 담당 | 맡는 곳 |
|---|---|---|
| A. 에이전트 백엔드 | 노윤지 | `backend/app/agent.py`, `backend/app/tools/plan_edit.py`, `backend/app/storage/`, `backend/app/voice/`(음성 입력 서명 URL), `backend/app/config.py`, `backend/scripts/`, `infra/`(SAM 템플릿·배포 구성) |
| B. 데이터·도구 | 강서영 | `backend/app/data/`, `backend/app/tools/lookup.py`, `backend/app/tools/schedule.py`(일정 시각 계산), `backend/app/tools/return_options.py`(귀가 분산), `backend/app/tools/kakao_route.py`(카카오 대중교통 경로), `backend/app/tools/transit.py`(대중교통 추정), `backend/app/tools/restaurants.py`(음식점), `backend/app/tools/events_map.py`(지도용 행사), `backend/app/speech/`(음성 출력 Polly), `backend/scripts/`의 데이터 수집·생성 스크립트(`fetch_*`, `build_*`, `backfill_names`, `extract_station_names`, `demo_lookup`, `demo_offline_check`)와 시드·CSV |
| C. 프론트엔드 | 이지혜 | `frontend/` (D 폴더 제외) |
| D. 아키텍처 설계 인프라 | 이온규 | `backend/app/guardian/`(예약 점검 로직 `scheduled.py` 포함), `backend/app/prompts.py`, `backend/app/photo/`(사진 인식 백엔드), `backend/eval/`, `frontend/src/features/local-card/`, `frontend/src/features/demo-panel/`, `frontend/src/features/data-notices/`(출처 표시·비 예보 배너) |

- D가 `frontend/` 안에 맡은 폴더는 C와 미리 합의한 하위 폴더에서만 작업합니다.
- 테스트는 각자 `backend/tests/test_<영역>.py` 파일에 씁니다. 다른 사람의 테스트 파일은 고치지 않습니다.
- 예약 점검은 로직을 `guardian/scheduled.py`(D)에 두고, Lambda 연결과 EventBridge 스케줄은 `infra/`(A)에서 합니다.
- 새 경로(`/plan/{plan_id}/delay`, `/alerts`, `/photo/*`, `/speak`, `/voice/url`)는 `docs/api-contract.md` 「v0.2 추가 경로」에 있습니다. 구현한 담당자가 `handler.py` 연결 PR을 따로 올립니다.

공용 파일 (뼈대 담당자 리뷰 필수):
- `backend/app/models/`
- `docs/api-contract.md`
- `backend/app/handler.py`
- `.kiro/steering/team.md`

## 브랜치
- `main`: 직접 push 금지
- 작업 브랜치: `feat/역할명` (예: `feat/guardian`, `feat/agent`, `feat/frontend`)
- `main`에서 분기하고, 머지 후 브랜치를 삭제합니다.
- develop 브랜치는 쓰지 않습니다.

## 커밋 메시지
- 형식: `type(scope): 요약`
- `type`: `feat`(기능), `fix`(수정), `docs`(문서), `test`(테스트), `chore`(설정·의존성), `refactor`(구조 변경)
- `scope`: `agent`, `tools`, `guardian`, `data`, `storage`, `models`, `handler`, `frontend`, `infra`, `docs`, `kiro`
- 예: `feat(guardian): 강수 점검 규칙 추가`, `fix(frontend): 배지 중복 표시 수정`

## PR 작성
- 제목: 커밋 메시지와 같은 형식
- 본문: PR 템플릿(`.github/pull_request_template.md`) 항목을 채웁니다.
- 크기: 변경 300줄 이하 권장. 넘으면 기능 단위로 나눕니다.
- Kiro 등 AI 도구로 만든 코드도 작성자가 diff를 직접 확인한 뒤 PR을 만듭니다.

## 리뷰와 머지 조건
| 변경 범위 | 리뷰 | 머지 |
|---|---|---|
| 자기 담당 영역만 | 생략 가능 | 본인 머지 |
| 공용 파일 | 뼈대 담당자 승인 | 승인 후 본인 머지 + 팀 채팅 공지 |
| 다른 사람 담당 영역 | 해당 담당자 승인 | 담당자가 머지 |
| 토 00:00 기능 동결 이후 전체 | 다른 1명이 데모 시나리오 실행 후 승인 | 승인자가 머지 |

API 계약을 바꿀 때는 `docs/api-contract.md`, `backend/app/models/`, `backend/app/data/` 샘플, 프론트엔드 mock 복사본을 같은 PR에서 함께 맞춥니다.

## 머지 절차
1. 최신 `main`을 받아 작업 브랜치를 rebase합니다.
   ```bash
   git fetch origin
   git rebase origin/main
   ```
2. 로컬에서 한 번 실행합니다.
   - 백엔드: `cd backend && uv run pytest -q`
   - 프론트엔드: `cd frontend && npm run build`
3. GitHub에서 **Squash and merge**로 머지합니다.
4. 원격 브랜치를 삭제합니다.

## 충돌 처리
- 자기 담당 영역 충돌: 본인이 해결합니다.
- 공용 파일 충돌: 양쪽 작성자가 함께 해결합니다. 한쪽 변경을 임의로 버리지 않습니다.
- 해결 후 머지 절차 2번(로컬 실행)을 다시 합니다.

## 시간 규칙
| 시각 | 규칙 |
|---|---|
| 금 18:00 이후 | 공용 파일 형식 변경은 팀 전원 합의 시에만 허용 |
| 토 00:00 | 기능 동결. 버그 수정, 평가, 데모 데이터만 허용. 셀프 머지 금지 |
| 토 03:00 | 코드 동결. `main`에 `demo-v1` 태그 생성 |
| 토 03:00 이후 | 데모를 막는 버그 수정만 허용. 수정 후 `demo-v2` 태그 |

```bash
git tag demo-v1 && git push origin demo-v1
```

## 되돌리기
- 머지된 PR에 문제가 있으면 GitHub의 **Revert** 버튼으로 되돌림 PR을 만듭니다. `main`에 강제 push하지 않습니다.
- 발표 직전 문제가 생기면 마지막 `demo-v*` 태그로 배포합니다.

## 커밋 금지 항목
- `.env`(`backend/.env` 포함), API 키, AWS 자격 증명
- 카카오 대중교통 경로 결과 (저장 자체 금지)
- 100MB 이상 파일 (대용량 데이터는 S3에 두고 경로만 기록)

키를 실수로 커밋하면 바로 팀에 알리고 그 키를 재발급합니다. 커밋을 지워도 기록에 남습니다.
