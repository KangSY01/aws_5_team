# 프론트엔드 (React + Vite)

부산 여행 일정 목록 화면. 백엔드의 `GET /plan/plan-1` 을 호출해 일정을 보여 준다.

## 백엔드 서버 시작

`backend/` 디렉터리에서 로컬 서버를 실행한다. 기본 주소는 `http://127.0.0.1:8000` 이다.

```bash
cd backend
uv run python -m scripts.local_server
```

## 프론트엔드 시작

`frontend/` 디렉터리에서 실행한다.

```bash
cd frontend
npm install      # 의존성 설치
npm run dev      # 개발 서버 시작
npm run build    # 프로덕션 빌드
npm test         # 테스트 실행 (vitest --run)
```

## 환경 변수 `VITE_API_BASE_URL`

백엔드 API 의 기준 주소(Base_URL)다. `.env.example` 을 `.env` 로 복사해 값을 바꿀 수 있다.

- 기본값: `http://127.0.0.1:8000`
- 미설정이거나 빈 문자열이면 기본값을 사용한다.

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```
