## 변경 요약
- 

## 변경 영역
- [ ] 에이전트 (A: `backend/app/agent.py`, `tools/plan_edit.py`, `storage/`, `voice/`)
- [ ] 데이터·도구 (B: `backend/app/data/`, `tools/lookup.py`, `speech/`)
- [ ] 프론트 (C: `frontend/`)
- [ ] Guardian·프롬프트·사진 인식·평가 (D: `backend/app/guardian/`, `prompts.py`, `photo/`, `backend/eval/`, `frontend/src/features/local-card/`, `demo-panel/`)
- [ ] 인프라·배포 (A: `infra/`)
- [ ] 문서·Kiro 설정 (`docs/`, `.kiro/`, `README.md` 등)
- [ ] 공용 파일 (`backend/app/models/`, `docs/api-contract.md`, `backend/app/handler.py`, `.kiro/steering/team.md`) → 뼈대 담당자 리뷰 필요, 팀 채팅 공지

## 공용 파일 변경 내용
공용 파일을 바꾼 경우에만 씁니다. 영향받는 담당자와, 함께 맞춘 파일(모델·샘플·프론트 mock)을 적습니다.
- 

## 확인 방법
- 

## 데모 시나리오 영향
- [ ] 영향 없음
- [ ] 영향 있음 (장면 번호와 내용):

## 체크리스트
- [ ] 최신 `main` 기준 rebase 완료
- [ ] 로컬 실행 확인 (`cd backend && uv run pytest -q` 또는 `npm run build`)
- [ ] `.env`·키 값·카카오 경로 결과 미포함
- [ ] AI 도구로 만든 코드의 diff 직접 확인
