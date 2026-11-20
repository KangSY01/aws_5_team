---
inclusion: fileMatch
fileMatchPattern: ["backend/app/tools/**", "backend/app/guardian/**", "backend/app/data/**", "backend/app/storage/**", "backend/tests/**"]
---

# 데이터 사용 규칙

해석 원칙의 원본은 `team.md`의 "데이터 해석 규칙"입니다. 이 문서는 API 세부 사항과 금지 사항을 덧붙입니다.

## 혼잡도 (한국관광공사 관광지 집중률)
- API: `https://apis.data.go.kr/B551011/TatsCnctrRateService/tatsCnctrRatedList`
- 파라미터: `serviceKey`, `pageNo`, `numOfRows`, `MobileOS`, `MobileApp`, `areaCd=26`, `signguCd`(부산 16개 구·군), `_type=json`
- 응답 필드: `baseYmd`, `areaCd`, `areaNm`, `signguCd`, `signguNm`, `tAtsNm`, `cnctrRate`
- `cnctrRate`는 관광지마다 자기 최고 시기를 100으로 둔 **상대값**입니다. 서로 다른 장소의 값을 비교하지 마십시오.
- 어디가 붐비는지는 부산시 월 방문자 합계(실제 인원), 언제 붐비는지는 집중률로 판단합니다.
- 일 단위 값입니다. 집중률로 시간대별 혼잡을 주장하지 마십시오.
- 요일 효과(부산 평균): 평일 42~44, 금 49, 토 67, 일 61
- 집중률에 없는 장소: 감천문화마을, 해동용궁사, 흰여울문화마을(터널만 존재), 해리단길, 블루라인파크. 요일 규칙으로 대체하십시오.
- 대형 행사는 집중률에 반영되지 않습니다. 행사일에는 행사 가중 규칙을 따로 적용하십시오.
- 도구: `get_crowd(place_id, date)` (`backend/app/tools/lookup.py`)

## 날씨 (기상청 단기예보, 공공데이터포털)
- API: `https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst`
- `base_time`: 0200, 0500, 0800, 1100, 1400, 1700, 2000, 2300 (발표 10분 후부터 조회 가능)
- 부산 격자 기본값: `nx=98`, `ny=76`
- 단기예보는 약 3일 이내만 제공됩니다. 그 이후 날짜는 "예보 없음"으로 처리하고, 데모는 `USE_MOCK=1`의 샘플 예보로 재현합니다.
- 도구: `get_weather(date)`

## 이동 시간 (추정표)
- 도구: `get_travel_time(from_place_id, to_place_id)`. `backend/app/data/travel_times.json`을 읽습니다(`USE_MOCK`과 무관). 표에 없는 장소 ID는 오류를 돌려줍니다.
- 표는 `uv run python -m scripts.build_travel_times`로 `places.json` 좌표에서 만듭니다. `places.json`이 바뀌면 다시 만드십시오.
- 추정 규칙: 경로 거리 = 직선거리 × 1.3. 경로 거리 1.2km 이하는 `walk`(시속 4.5km), 그보다 멀면 `subway`(평균 시속 25km + 대기·환승 10분). 분은 올림하고 양방향은 같은 값입니다.
- 실제 경로 조회 값이 아닙니다. 답변에서는 "약 N분"으로 말하고 노선·환승을 단정하지 마십시오.
- 카카오 경로 API는 지금 쓰지 않습니다. 쓰게 되더라도 결과를 저장하지 않습니다(아래 금지 사항).

## 행사 (한국관광공사 행사정보)
- API: `https://apis.data.go.kr/B551011/KorService2/searchFestival2` (`lDongRegnCd=26`, `eventStartDate`, `eventEndDate`)
- `uv run --env-file .env python -m scripts.fetch_events`가 2026-11 기준으로 한 번 받아 `backend/app/data/events.json`에 저장합니다. `--offline`은 호출 없이 저장된 응답으로 다시 만듭니다.
- `start`·`end`는 행사 기간의 첫날 00:00, 마지막 날 23:59입니다. API는 날짜만 주므로 하루 중 진행 시간은 모릅니다.
- `place_ids`는 행사 좌표에서 직선거리 1km 이내인 `places.json` 장소입니다.
- `events.json`에는 받은 행사를 모두 둡니다(행사 레이어 표시용).
- 도구: `get_events(date)`. 행사일만 돌려줍니다. 기간이 7일 이하(첫날·마지막 날 포함)인 행사는 기간 전체(`kind: "short"`), 7일보다 긴 행사는 개막일에만(`kind: "opening_day"`) 나옵니다. 상설 행사가 매일 행사 가중을 받지 않게 하기 위한 규칙입니다.
- 목록에 없는 행사는 있다고 말하지 마십시오.

## 날씨 샘플 (`backend/app/data/weather/`)
- 파일 형식은 `get_weather` 반환값과 같습니다(`{"date", "hourly"}`, 설명용 `note`는 선택). 파일 이름은 소문자·숫자·하이픈만 씁니다.
- `{YYYY-MM-DD}.json`: `USE_MOCK=1`일 때 `get_weather`가 그 날짜의 예보로 씁니다. 파일이 없는 날짜는 예보 없음(`hourly: []`)입니다.
- 그 밖의 이름(`rain-afternoon.json` 등): 데모 스위치 `demo.weather_preset`으로만 씁니다.

## 장소 정보
- 한국관광공사 다국어 관광정보서비스(영문·일문·중문 번체, 중문 간체는 신청 후 사용)와 부산시 명소정보를 사용하십시오.
- 운영시간·요금·휴무일은 도구 결과에 있는 값만 쓰십시오. 없으면 모른다고 답하고 지어내지 마십시오.
- `backend/app/data/places.json`의 좌표, 다국어 이름, 가까운 역은 아직 검증하지 않은 값입니다. 공공데이터로 교체하기 전에는 사실처럼 단정하지 마십시오.

## 금지 사항
- 카카오 대중교통 경로 API 결과를 저장·캐시하지 마십시오. 실시간 호출만 허용됩니다.
- 네이버 블로그·검색 결과를 수집하거나 AI로 가공하지 마십시오.
- 공공데이터 원문을 화면에 표시할 때 출처를 함께 표기하십시오. 백엔드는 출처를 `sources`에 담습니다.

## 계산과 생성의 역할 구분
- LLM 담당: 장소 선택, 이유 설명, 다국어 문장
- 코드 담당: 방문 순서·시각 계산, 이동 시간, 수치, 장소 ID 검증, Guardian 점검과 해결안 탐색
- LLM 응답에 포함된 장소 ID가 `backend/app/data/places.json`에 없으면 버리고 다시 시도하십시오.
