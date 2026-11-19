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
