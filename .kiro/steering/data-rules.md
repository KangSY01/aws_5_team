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
- `uv run python -m scripts.build_congestion`이 팀원이 받은 원본(`backend/app/data/raw/congestion_busan.json`, git에 올리지 않음)에서 우리 장소만 뽑아 `backend/app/data/congestion.json`을 만듭니다. API를 부르지 않습니다.
- 장소 연결은 `build_congestion.PLACE_NAMES` 표의 이름(`tAtsNm`)과 정확히 같은 항목만 씁니다. 비슷한 이름을 자동으로 찾지 않습니다.
- 받아 둔 기간은 2026-11-18 ~ 2026-12-17(30일)입니다. 기간 밖 날짜는 집중률이 없는 것으로 처리합니다.
- 집중률이 있는 장소(21곳): 해운대·광안리·송정해수욕장, 자갈치시장, 국제시장, 해운대시장, 태종대, 범어사, 동백섬, 더베이101, 청사포 다릿돌전망대, 씨라이프부산아쿠아리움, 부산시립미술관, 민락수변공원, 롯데월드 어드벤처 부산, 용두산공원, 송도해상케이블카, 국립해양박물관, 부산 차이나타운, 부산박물관, 부산시민공원.
- 집중률에 없는 장소(12곳, 연결 표에 없음): 감천문화마을, 부산타워, 해동용궁사, 신세계백화점 센텀시티점, 해리단길, 블루라인파크, 부산엑스더스카이, 영화의전당, 롯데프리미엄아울렛 동부산점, 흰여울문화마을, 부산근현대역사관, 초량이바구길. 요일 규칙으로 대체하십시오.
- 대형 행사는 집중률에 반영되지 않습니다. 행사일에는 행사 가중 규칙을 따로 적용하십시오.
- 도구: `get_crowd(place_id, date)` (`backend/app/tools/lookup.py`). `congestion.json`에 값이 있으면 `ratio`=값, `source: "concentration"`. 없으면 `ratio: null`, `source: "weekday_rule"`.

## 날씨 (기상청 단기예보, 공공데이터포털)
- API: `https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst`
- `base_time`: 0200, 0500, 0800, 1100, 1400, 1700, 2000, 2300 (발표 10분 후부터 조회 가능)
- 부산 격자 기본값: `nx=98`, `ny=76`
- 단기예보는 약 3일 이내만 제공됩니다. 그 이후 날짜는 "예보 없음"으로 처리하고, 데모는 `USE_MOCK=1`의 샘플 예보로 재현합니다.
- 도구: `get_weather(date)`
- 캐시(`USE_MOCK=0`일 때만): DynamoDB `busan-guide-cache`(환경 변수 `CACHE_TABLE`)에 `pk="WEATHER#<날짜>"`, `sk="KMA"`로 `hourly`, `fetched_at`, `base_time`(기상청 발표 시각), `ttl`(`fetched_at` + 2일)을 저장합니다. 예보 범위 밖 날짜와 빈 예보는 저장하지 않습니다.
- `fetched_at`이 60분 이내면 기상청을 부르지 않고 캐시를 돌려줍니다. 기상청 호출이 실패하면 60분이 넘은 캐시라도 돌려주고(`cache.stale: true`), 캐시도 없으면 오류입니다. DynamoDB가 실패하면 경고 로그만 남기고 캐시 없이 동작합니다.
- 반환값에 `cache: {"hit", "stale", "fetched_at"}`가 붙습니다. `stale`이 `true`면 오래된 예보일 수 있다고 안내하십시오. `USE_MOCK=1`은 캐시를 쓰지 않고 `cache` 필드도 없습니다.

## 이동 시간 (추정표)
- 도구: `get_travel_time(from_place_id, to_place_id)`. `backend/app/data/travel_times.json`을 읽습니다(`USE_MOCK`과 무관). 표에 없는 장소 ID는 오류를 돌려줍니다.
- 표는 `uv run python -m scripts.build_travel_times`로 `places.json` 좌표에서 만듭니다. `places.json`이 바뀌면 다시 만드십시오.
- 추정 규칙: 경로 거리 = 직선거리 × 1.3. 경로 거리 1.2km 이하는 `walk`(시속 4.5km), 그보다 멀면 `subway`(평균 시속 25km + 대기·환승 10분). 분은 올림하고 양방향은 같은 값입니다.
- 실제 경로 조회 값이 아닙니다. 답변에서는 "약 N분"으로 말하고 노선·환승을 단정하지 마십시오.
- 카카오 경로 API는 지금 쓰지 않습니다. 쓰게 되더라도 결과를 저장하지 않습니다(아래 금지 사항).

## 행사 (한국관광공사 행사정보)
- API: `https://apis.data.go.kr/B551011/KorService2/searchFestival2` (`lDongRegnCd=26`, `eventStartDate`, `eventEndDate`)
- `uv run --env-file .env python -m scripts.fetch_events`가 2026-11 기준으로 한 번 받아 `backend/app/data/events.json`에 저장합니다. `--offline`은 호출 없이 저장된 응답으로 다시 만듭니다.
- `start`·`end`는 행사 기간의 첫날 00:00, 마지막 날 23:59입니다. 행사 목록 API는 날짜만 주므로 하루 중 진행 시간은 모릅니다.
- 행사 시간을 따로 확인한 행사(`fetch_events.PLAYTIME_CONTENT_IDS`, 지금은 해운대 빛축제)는 `detailIntro2`(`contentTypeId=15`)의 `playtime` 원문을 `playtime_raw`에 둡니다. 원문이 `18:00~23:00` 같은 한 구간이면 `start`는 첫날 18:00, `end`는 마지막 날 23:00으로 씁니다(기간 중 매일 그 시간). 애매하면 시각은 바꾸지 않습니다.
- `place_ids`는 행사 좌표에서 직선거리 1km 이내인 `places.json` 장소입니다.
- `main_place_id`(행사 대표 장소)는 `place_ids` 중 행사 좌표와 직선거리가 가장 가까운 장소입니다. 거리가 같으면 `place_id` 사전순이고, `place_ids`가 비면 `null`입니다. `get_events`도 이 값을 돌려줍니다.
- `events.json`에는 받은 행사를 모두 둡니다(행사 레이어 표시용).
- 도구: `get_events(date)`. 행사일만 돌려줍니다. 기간이 7일 이하(첫날·마지막 날 포함)인 행사는 기간 전체(`kind: "short"`), 7일보다 긴 행사는 개막일에만(`kind: "opening_day"`) 나옵니다. 상설 행사가 매일 행사 가중을 받지 않게 하기 위한 규칙입니다. 반환값의 `start`·`end`는 요청한 날짜의 행사 시간대입니다(행사 시간을 아는 행사는 그 시간, 모르면 그날 00:00~23:59). 원래 기간은 `period_start`·`period_end`로 함께 돌려줍니다. `kind`는 원래 기간으로 정합니다.
- 목록에 없는 행사는 있다고 말하지 마십시오.

## 역 표 (부산교통공사 도시철도 역 정보)
- `uv run python -m scripts.build_stations`가 `backend/scripts/busan_stations.csv`(1~4호선, 데이터 114행)에서 `backend/app/data/stations.json`(108곳)을 만듭니다. API를 부르지 않습니다. CSV나 `places.json`이 바뀌면 다시 만드십시오.
- `station`은 CSV의 `name_en` 그대로이며, `places.json`의 `nearest_station`과 정확히 같은 문자열일 때만 연결합니다. 역 이름을 새로 만들지 않습니다.
- 환승역 6곳(Seomyeon, Yeonsan, Dongnae, Suyeong, Deokcheon, Minam)은 한 항목으로 합치고 좌표는 행들의 평균입니다. `lines`는 참고용이며 노선·환승을 단정하지 마십시오.
- 동해선·경전철 역은 없습니다. `nearest_station` 중 표에 없는 값은 `OSIRIA`(해동용궁사) 하나이고, 스크립트가 경고로 출력합니다.
- CSV의 `name_en` 5개(교대, 부산대, 경성대부경대, 국제금융센터부산은행, 부산대양산캠퍼스)는 원본의 이중 이스케이프(`Nat''''''''l`)를 작은따옴표 1개로 복원했습니다(`Pusan Nat'l Univ.` 등). 다른 값은 원본 그대로입니다.
- 도구: `get_return_options` (`backend/app/tools/return_options.py`). 역 사이 시간은 이 표의 좌표와 `travel_times.json`의 `rule`로 계산한 추정이며, 역 혼잡과 혼잡 시간대는 규칙 기반 가정입니다(실측·실시간 아님).

## 날씨 샘플 (`backend/app/data/weather/`)
- 파일 형식은 `get_weather` 반환값과 같습니다(`{"date", "hourly"}`, 설명용 `note`는 선택). 파일 이름은 소문자·숫자·하이픈만 씁니다.
- `{YYYY-MM-DD}.json`: `USE_MOCK=1`일 때 `get_weather`가 그 날짜의 예보로 씁니다. 파일이 없는 날짜는 예보 없음(`hourly: []`)입니다.
- 그 밖의 이름(`rain-afternoon.json` 등): 데모 스위치 `demo.weather_preset`으로만 씁니다. `rain-afternoon.json`은 2026-11-28 13:00~15:00 비(13·14시 칸)입니다.

## 운영시간 (한국관광공사 소개정보)
- API: `https://apis.data.go.kr/B551011/KorService2/detailIntro2` (`contentId`, `contentTypeId`). 장소당 1회 호출합니다.
- `uv run --env-file .env python -m scripts.fetch_hours`가 `backend/app/data/hours.json`을 만듭니다. 저장된 응답이 있는 장소는 다시 부르지 않습니다. `--offline`은 호출 없이 다시 만듭니다.
- 관광타입마다 필드 이름이 다릅니다: 관광지(12) `usetime`·`restdate`, 문화시설(14) `usetimeculture`·`restdateculture`, 쇼핑(38) `opentime`·`restdateshopping`.
- `opens`·`closes`는 원문이 `HH:MM~HH:MM` 한 구간일 때만 넣습니다(뒤의 "(입장 마감 17:30)"은 무시). 계절·요일별 시간, 24:00 마감, "상시 개방"은 `null`입니다.
- `closed_weekdays`는 "매주 ○요일"만 넣습니다. "월요일이 공휴일이면 다음 날 휴관" 같은 예외와 "1월 1일" 같은 날짜는 반영하지 않습니다(`closed_dates`는 빈 목록). "점포 별로 상이"·"일부" 같은 단서가 붙은 휴무(국제시장)도 넣지 않습니다.
- `raw_text`는 API의 한국어 원문입니다. 위 값으로 바꾸지 못한 내용은 여기에만 있습니다.
- 영화의전당은 국문 항목이 자료실이라 모르는 값으로 둡니다(`fetch_hours.NOT_THE_PLACE`).
- 도구: `get_hours(place_id)`

## 큐레이션 (규칙으로 만든 참고 값)
- `uv run python -m scripts.build_curation`이 `backend/app/data/curation.json`을 만듭니다. API를 부르지 않습니다. `places.json`·`travel_times.json`이 바뀌면 다시 만드십시오.
- `tags`: `category`와 TourAPI 분류 코드(`lclsSystm1`·`lclsSystm2`)에서 매핑한 값입니다. 매핑 표는 `build_curation.py`의 `CATEGORY_TAGS`·`LCLS_TAGS`입니다.
- `foreigner_friendly`(0~3): 다국어 관광정보 제공 언어 수(영어·일본어·중국어 중 이름이 있는 언어 수)입니다. 현장의 외국어 안내 수준이 아닙니다.
- `crowd_alternatives`: 이동 시간 30분 이내이고 `indoor`를 뺀 `tags`가 하나 이상 겹치는 장소, 가까운 순 최대 3곳.
- `rain_alternatives`: 이동 시간 30분 이내의 실내(`indoor=true`) 장소, 가까운 순 최대 3곳.
- 사람이 고친 항목은 `curation_overrides.json`에 두면 다시 만들 때 덮어쓰고 `source`가 `"manual"`이 됩니다.
- 도구: `get_place_info(place_id)`. `Place` + `curation` + `hours`를 한 번에 돌려줍니다. `search_places` 결과에는 큐레이션을 넣지 않습니다.
- 대체 후보는 후보일 뿐입니다. 그 장소의 실제 혼잡·날씨는 `get_crowd`·`get_weather`로 확인하십시오.

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
