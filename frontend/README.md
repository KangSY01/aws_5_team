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

## 지도 타일 출처

별도 래스터 타일을 사용하려면 `VITE_MAP_TILE_URL`에 타일 주소를, `VITE_MAP_TILE_ATTRIBUTION`에 공급자가 안내한 출처 문구와 링크를 설정합니다. 출처에는 링크를 포함한 HTML을 사용할 수 있습니다. 기본 OpenStreetMap 래스터 타일에는 OpenStreetMap 출처가 자동으로 표시됩니다.

벡터 타일 공급자를 바꿀 때는 `public/maps/busan-poster.json`의 해당 소스에서 URL과 `attribution`을 함께 갱신합니다. 스타일에 출처를 지정하지 않으면 소스의 TileJSON 출처를 사용합니다.

## 환경 변수 `VITE_API_BASE_URL`

백엔드 API 의 기준 주소(Base_URL)다. `.env.example` 을 `.env` 로 복사해 값을 바꿀 수 있다.

- 기본값: `http://127.0.0.1:8000`
- 미설정이거나 빈 문자열이면 기본값을 사용한다.

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 샘플 mock 데이터 (`src/mocks/`)

테스트와 화면 확인에 쓰는 mock 은 백엔드 샘플 데이터를 그대로 복사한 것이다.

| 복사본 | 원본 |
| --- | --- |
| `frontend/src/mocks/sample_plan.json` | `backend/app/data/sample_plan.json` |
| `frontend/src/mocks/places.json` | `backend/app/data/places.json` |

동기화 규칙:

- 원본(`backend/app/data/`)이 바뀌면 같은 PR 에서 복사본도 똑같이 맞춘다.
- 복사본은 읽기 전용으로 취급한다. 내용을 직접 고치지 않고, 항상 원본을 먼저 고친 뒤 다시 복사한다.
- 원본 파일은 프론트엔드 작업에서 수정하지 않는다.

복사 방법 (저장소 루트에서 실행):

```bash
# macOS / Linux / Git Bash
cp backend/app/data/sample_plan.json frontend/src/mocks/sample_plan.json
cp backend/app/data/places.json frontend/src/mocks/places.json
```

```bat
:: Windows cmd
copy /Y backend\app\data\sample_plan.json frontend\src\mocks\sample_plan.json
copy /Y backend\app\data\places.json frontend\src\mocks\places.json
```
