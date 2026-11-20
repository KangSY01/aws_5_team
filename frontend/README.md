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

## 행사 지도와 AI 일정 데모

홈 지도는 `src/mocks/events.js`의 예시 행사 네 건을 사용하며 행사 카드에 샘플임을 표시합니다. API 주소를 설정하지 않으면 일정과 대체안은 `src/lib/demoPlanner.js`에서 로컬 장소 목록으로 생성합니다. 단일 데모 사용자를 전제로 하며 코스, 작성 중인 여행 취향, 활성 여행은 브라우저에 저장합니다.

지도 점선은 방문 순서를 보여줍니다. 실시간 AI, 도보 길찾기, 영업시간·식단·숙박 정보에는 별도 데이터나 API가 필요합니다. 데모 흐름에 백엔드 설정은 필요하지 않습니다.

## 지도 타일 출처

여행 취향 지도는 메인 지도를 재사용합니다. 권역 마커는 대표 장소의 좌표에 고정되며, 가까운 마커는 연결선으로 실제 위치를 가리킵니다.

지역 카드의 사진은 미리보기 크기에 맞춰 축소해 저장하고 화면에 맞게 잘라 표시합니다. 각 카드의 출처 링크에서 Wikimedia Commons 원본과 라이선스를 확인할 수 있습니다.

새 권역의 프론트 데모 장소 여섯 곳은 기존 장소 형식에 맞춰 `src/mocks/regionalPlaces.json`에 저장합니다. 좌표는 OpenStreetMap과 OpenFreeMap에서 확인했습니다. 이 파일은 백엔드 샘플을 갱신할 때 덮어쓰지 않습니다.

별도 래스터 타일을 사용하려면 `VITE_MAP_TILE_URL`에 타일 주소를, `VITE_MAP_TILE_ATTRIBUTION`에 공급자가 안내한 출처 문구와 링크를 설정합니다. 출처에는 링크를 포함한 HTML을 사용할 수 있습니다. 기본 OpenStreetMap 래스터 타일에는 OpenStreetMap 출처가 자동으로 표시됩니다.

벡터 타일 공급자를 바꿀 때는 `public/maps/busan-poster.json`의 해당 소스에서 URL과 `attribution`을 함께 갱신합니다. 스타일에 출처를 지정하지 않으면 소스의 TileJSON 출처를 사용합니다.

## 환경 변수 `VITE_API_BASE_URL`

백엔드 API 의 기준 주소(Base_URL)다. `.env.example` 을 `.env` 로 복사해 값을 바꿀 수 있다.

- 일정 화면에서 실제 API를 사용하려면 `frontend/.env.local`에 배포된 Function URL을 설정하고 Vite를 다시 시작합니다.
- 설정한 경우 일정 생성과 수정은 일반 JSON `POST /chat`을 사용하며, 프론트의 채팅 요청 제한 시간은 60초입니다.
- 일정 조회 클라이언트 기본값: `http://127.0.0.1:8000`
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

## 번역 탭

사진 번역은 기존 `VITE_API_BASE_URL`을 사용합니다. `POST /photo/upload-url`로 받은 URL에 JPEG 또는 PNG를 직접 업로드한 뒤 `POST /photo/translate`를 호출합니다. 한국어 원문을 영어, 일본어, 중국어 간체 또는 번체로 번역하며, 번역 요청은 최대 60초 기다립니다. 음성 입력은 브라우저의 음성 인식을 사용하며, 지원 여부는 기기와 브라우저에 따라 달라집니다.

모바일에서 번역 결과를 받으려면 빌드 전에 `VITE_TRANSLATION_ENDPOINT`를 설정합니다. 이 주소는 JSON `POST` 요청 `{ q, source, target, format: "text" }`을 받아 `{ translatedText }`를 반환해야 합니다. `source`와 `target`은 `ko`, `en`, `ja`, `zh-Hans`, `zh-Hant` 중 하나입니다. 제공자 키는 이 주소를 처리하는 서버에 두고, 브라우저에는 공개 주소만 설정합니다. 별도 주소를 설정하지 않으면 브라우저 내장 Translator API가 지원되는 환경에서 번역합니다.
