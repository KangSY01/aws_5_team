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
- 집중률에 없는 장소(14곳, 연결 표에 없음): 감천문화마을, 부산타워, 해동용궁사, 신세계백화점 센텀시티점, 해리단길, 블루라인파크, 부산엑스더스카이, 영화의전당, 롯데프리미엄아울렛 동부산점, 흰여울문화마을, 부산근현대역사관, 초량이바구길, 해운대 로데오거리, 부산 영화의 거리. 요일 규칙으로 대체하십시오.
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
- `get_travel_time`·`build_plan`·Guardian은 이 추정을 그대로 씁니다. 카카오 경로는 부르지 않습니다(아래 「카카오 대중교통 경로」).

## 카카오 대중교통 경로 (실시간 호출)
- API: 카카오맵 대중교통 경로 조회 `https://dapi.kakao.com/v2/routing/publictraffic` (`backend/app/tools/kakao_route.py`의 `fetch_routes`).
- 장면 7 귀가 경로(`get_return_options`)의 역 사이 시간에만 실시간으로 호출합니다. 도구 호출 한 번에 출발역마다 1회, 3초 제한이며 다시 시도하지 않습니다.
- 결과를 저장·캐시하지 않습니다(파일·DynamoDB·메모리 캐시 모두). 오프라인 캐시 모드에도 넣지 않습니다(아래 금지 사항).
- 호출이 실패하거나 `USE_MOCK=1`이거나 키가 없으면 역 좌표 추정으로 대체합니다. 항목마다 `time_source`(`"kakao"` / `"estimate"`)로 구분합니다.
- `time_source`가 `"kakao"`인 항목에서만 노선·환승(`legs`, `transfers`)을 카카오 값으로 말하십시오. `"estimate"`인 항목은 "약 N분"으로 말하고 노선·환승을 단정하지 마십시오.
- 키는 환경 변수 `KAKAO_REST_API_KEY`로만 읽습니다. 커밋하거나 로그에 남기지 마십시오.
- 테스트는 `tests/conftest.py`의 `no_kakao`가 실제 호출을 막습니다. 카카오 성공은 `tests/test_return_options_kakao.py`에서 직접 만든 경로로만 확인합니다.

## 카카오 로컬 키워드 검색 (실시간 호출)
- API: 카카오 로컬 키워드 검색 `https://dapi.kakao.com/v2/local/search/keyword.json` (`backend/app/tools/activities.py`의 `find_activities`).
- `GET /activities?area=&kind=`(채팅 놀거리 카드)에서만 호출합니다. 요청 한 번에 1회, 5초 제한, 최대 5곳이며 다시 시도하지 않습니다. 주소가 "부산 "으로 시작하는 결과만 돌려줍니다.
- 결과를 저장·캐시하지 않습니다. 운영시간·사진·평점은 응답에 없으므로 답변에서 말하지 마십시오.
- 키가 없으면 `503 activities_unavailable`, 호출 실패는 `502`입니다. `USE_MOCK=1`이어도 키가 있으면 호출합니다.
- 이 결과는 places.json의 장소가 아닙니다. place_id로 쓰거나 일정 도구에 넘기지 마십시오.

## 행사 (한국관광공사 행사정보)
- API: 한국어·영어·일본어·중국어 간체·번체 TourAPI `searchFestival2` (`lDongRegnCd=26`, `eventStartDate`, `eventEndDate`). 서비스는 `KorService2`, `EngService2`, `JpnService2`, `ChsService2`, `ChtService2`입니다.
- `uv run --env-file .env python -m scripts.fetch_events --reuse-raw`가 2026-11 기준 목록을 언어별 1회씩 받아 `backend/app/data/events.json`에 저장합니다. 같은 요청의 raw는 재사용하고, `--offline`은 호출 없이 다시 만듭니다.
- `names.ko`는 국문 행사명입니다. 외국어 이름은 `fetch_places`와 같은 규칙으로 외국어 제목에 붙은 한국어와 국문 제목을 비교하고, 300m 우선·1km 보충 거리 안에서 일치할 때만 넣습니다. 못 찾은 언어는 생략하며 번역해서 만들지 않습니다.
- `type`은 TourAPI 원본 `lclsSystm2`·`lclsSystm3`(없으면 `cat2`·`cat3`)를 `festival` / `performance` / `exhibition` / `event`로 바꾼 값입니다. EV01은 축제, EV02는 공연, EV0302는 전시·박람회, 나머지 EV03은 행사입니다.
- `start`·`end`는 행사 기간의 첫날 00:00, 마지막 날 23:59입니다. 행사 목록 API는 날짜만 주므로 하루 중 진행 시간은 모릅니다.
- 행사 시간을 따로 확인한 행사(`fetch_events.PLAYTIME_CONTENT_IDS`, 지금은 해운대 빛축제)는 `detailIntro2`(`contentTypeId=15`)의 `playtime` 원문을 `playtime_raw`에 둡니다. 원문이 `18:00~23:00` 같은 한 구간이면 `start`는 첫날 18:00, `end`는 마지막 날 23:00으로 씁니다(기간 중 매일 그 시간). 애매하면 시각은 바꾸지 않습니다.
- `place_ids`는 행사 좌표에서 직선거리 1km 이내인 `places.json` 장소입니다.
- `main_place_id`(행사 대표 장소)는 `place_ids` 중 행사 좌표와 직선거리가 가장 가까운 장소입니다. 거리가 같으면 `place_id` 사전순이고, `place_ids`가 비면 `null`입니다. `get_events`도 이 값을 돌려줍니다.
- `events.json`에는 받은 행사를 모두 둡니다. 지도는 `GET /events?date=YYYY-MM-DD`(`app/tools/events_map.py`)를 쓰며, 조회 날짜가 전체 기간에 포함된 행사를 장·단기와 관계없이 모두 돌려줍니다.
- Guardian 도구 `get_events(date)`는 별도 규칙을 유지합니다. 기간이 7일 이하(첫날·마지막 날 포함)인 행사는 기간 전체(`kind: "short"`), 7일보다 긴 행사는 개막일에만(`kind: "opening_day"`) 나옵니다. 상설 행사가 매일 행사 가중을 받지 않게 하기 위한 규칙입니다. 반환값의 `start`·`end`는 요청한 날짜의 행사 시간대입니다(행사 시간을 아는 행사는 그 시간, 모르면 그날 00:00~23:59). 원래 기간은 `period_start`·`period_end`로 함께 돌려줍니다. `kind`는 원래 기간으로 정합니다.
- 목록에 없는 행사는 있다고 말하지 마십시오.

## 역 표 (부산교통공사 도시철도 역 정보)
- `uv run python -m scripts.build_stations`가 `backend/scripts/busan_stations.csv`(1~4호선, 데이터 114행)에서 `backend/app/data/stations.json`(108곳)을 만듭니다. API를 부르지 않습니다. CSV나 `places.json`이 바뀌면 다시 만드십시오.
- `station`은 CSV의 `name_en` 그대로이며, `places.json`의 `nearest_station`과 정확히 같은 문자열일 때만 연결합니다. 역 이름을 새로 만들지 않습니다.
- 환승역 6곳(Seomyeon, Yeonsan, Dongnae, Suyeong, Deokcheon, Minam)은 한 항목으로 합치고 좌표는 행들의 평균입니다. `lines`는 참고용이며 노선·환승을 단정하지 마십시오.
- 동해선·경전철 역은 없습니다. `nearest_station` 중 표에 없는 값은 `OSIRIA`(해동용궁사) 하나이고, 스크립트가 경고로 출력합니다.
- CSV의 `name_en` 5개(교대, 부산대, 경성대부경대, 국제금융센터부산은행, 부산대양산캠퍼스)는 원본의 이중 이스케이프(`Nat''''''''l`)를 작은따옴표 1개로 복원했습니다(`Pusan Nat'l Univ.` 등). 다른 값은 원본 그대로입니다.
- `names`(`ja`, `zh-Hans`, `zh-Hant`, 키는 `places.json`의 `names`와 같음)는 2호선 역에만 있습니다. 국가철도공단 부산 2호선 역명 데이터(기준일 2026-06-30)를 옮긴 `backend/scripts/busan_line2_station_names.csv`의 한글 역명을 '역'과 괄호 표기를 떼고 `name_ko`와 비교해 넣습니다(일본어 40곳, 간체·번체 39곳). 이름이 안 맞는 2호선 역 3곳(시립미술관, 경성대부경대, 국제금융센터부산은행)과 2호선 밖 역, 빈 칸은 넣지 않고 지어내지 않습니다.
- 도구: `get_return_options` (`backend/app/tools/return_options.py`). 역 사이 시간은 이 표의 좌표로 카카오 대중교통 경로를 실시간 호출해 쓰고(위 「카카오 대중교통 경로」), 실패·`USE_MOCK=1`·키 없음이면 이 표의 좌표와 `travel_times.json`의 `rule`로 계산한 추정으로 대체합니다(`time_source`로 구분). 역 혼잡과 혼잡 시간대는 규칙 기반 가정입니다(실측·실시간 아님).

## 막차 시각 (부산교통공사 표준 열차시각표)
- API: 공공데이터포털 「부산교통공사_부산도시철도 열차시각표 조회 서비스_GW」, 서비스 URL `https://apis.data.go.kr/B551542/trainTime/getTrainTime`.
- 파라미터: `serviceKey`, `pageNo`, `numOfRows`, `scode`(CSV 역번호), `stime`·`etime`(시분 4자리), `enum`, `act=json`. 응답에는 `day`·`updown` 요청 값과 관계없이 모든 요일·방향이 섞여 오므로 두 값은 고정해 보내고, 역마다 시간 구간 두 개(22:00~23:59, 00:00~01:30)만 받아 코드에서 `scode`·`line`·`dayType`(`1` 평일 / `2` 토요일 / `3` 일요일·공휴일)·`updown`(`0` 상행 / `1` 하행)으로 거릅니다. 목적지 전에 끝나는 열차(`endcode`가 목적지에 못 미침)는 빼고, 남은 `arrtime` 중 가장 늦은 값을 막차로 씁니다(자정 뒤는 24시 이상으로 둠).
- `uv run --env-file .env python -m scripts.fetch_last_trains --reuse-raw`가 Haeundae·Dongbaek·Jung-dong의 Seomyeon 방향과 Seomyeon의 Haeundae 방향을 요일 구분별로 받아 `backend/app/data/last_trains.json`에 막차만 저장합니다. 같은 raw는 다시 호출하지 않으며 `--offline`도 지원합니다.
- 역번호는 `backend/scripts/busan_stations.csv`의 2호선 행(203·204·202·219)만 읽습니다. 방향은 2호선 역번호가 작아지는 상행(`0`, 해운대 방향)과 커지는 하행(`1`, 서면 방향)으로 정합니다.
- `get_return_options`의 `shift_later`는 해당 역·방향·요일 데이터가 있으면 제안 출발 시각과 막차를 비교합니다. 막차 뒤면 `last_train_missed`, 막차 시각과 같거나 앞이면 막차 경고가 없습니다. 행이나 파일이 없으면 `last_train_unknown`입니다.
- 평일 공휴일을 식별할 휴일 달력은 저장하지 않았습니다. 코드는 월~금은 평일, 토요일은 토요일, 일요일은 일요일·공휴일 표를 고릅니다. 표준 도착시각이므로 실제 운행 시각과 다를 수 있습니다.

## 대중교통 (역 표와 좌표 기반 추정)
- 도구: `get_transit_info(from_place_id, to_place_id=None, to_station=None)` (`backend/app/tools/transit.py`). `to_station`(영문 역 이름)이 `to_place_id`보다 우선합니다. 파일(`places.json`, `stations.json`, `travel_times.json`의 `rule`)만 읽고 외부 API를 부르지 않습니다.
- 돌려주는 값: 양쪽의 가까운 역(`nearest_station`), 역에 서는 호선(`lines`), 장소↔역 도보 분, 역 사이 지하철 추정 분, 합계(`total_min`). 계산은 `return_options.py`의 `walk_minutes`·`subway_minutes`와 같습니다(직선거리 × 1.3, 도보 시속 4.5km, 지하철 시속 25km + 10분, 올림).
- 모두 추정입니다. "약 N분"으로 말하고, 타는 호선·환승 여부·환승 횟수를 단정하지 마십시오. `lines`는 참고 값입니다.
- 제한된 막차 표는 `last_trains.json`에 있는 네 역·두 방향에만 씁니다. 그 밖의 시간표, 실시간 도착, 첫차, 배차 간격, 요금, 환승 도보는 데이터에 없습니다(`basis.not_included`). 지어내지 마십시오.
- 역 표에는 1~4호선만 있습니다. 동해선·경전철 역이 가까운 장소(해동용궁사 등)와 `nearest_station`이 `null`인 장소는 `no_station` 오류입니다.
- 역까지 걷는 추정이 20분을 넘으면 그쪽 `warnings`에 `far_from_station`이 붙습니다.

## 음식점 (한국관광공사 TourAPI 음식점 정보)
- 수집: `uv run --env-file .env python -m scripts.fetch_restaurants`가 `backend/app/data/restaurants.json`을 만듭니다. `--reuse-raw`는 저장된 응답을 다시 부르지 않고, `--offline`은 호출 없이 다시 만듭니다. 원본 응답은 `backend/app/data/raw/restaurants/`에 두고 git에 올리지 않습니다.
- API: 국문 `KorService2/areaBasedList2`(`contentTypeId=39`, `lDongRegnCd=26`, 부산 전체 약 510건)를 받아 기준 좌표에서 500m 이내만 고릅니다. `locationBasedList2`는 항목을 빠뜨려 쓰지 않습니다(해운대해수욕장 500m에서 1건, 같은 범위에 실제로는 11건).
- 기준(`scripts/restaurant_seeds.json`): 장소 `haeundae-beach`, `jagalchi-market`, `gamcheon-village`와 역 `Seomyeon`. `places.json`·`stations.json`에 있는 값만 씁니다. 기준이 아닌 곳은 `restaurants_not_collected` 오류입니다.
- 외국어 이름: 외국어 서비스 `areaBasedList2`(`contentTypeId=82`)에서 `fetch_places`와 같은 일치 규칙으로 찾습니다. 외국어 음식점은 부산 전체에 언어별 수십 건뿐이라 대부분 이름이 없습니다(43곳 중 4곳). 없으면 `name_ko`를 쓰고, 빠진 항목은 `restaurants_review.csv`에 남습니다.
- `restaurant_id`(`kto-<국문 contentid>`)는 `place_id`가 아닙니다. 일정에 넣거나 장소 ID로 쓰지 마십시오.
- `cuisine`은 국문 분류 코드(`lclsSystm3`)를 `fetch_restaurants.CUISINE_BY_CLASS`로 바꾼 값입니다(표에 없으면 `null`). `menu_raw`는 기준마다 가까운 5곳만 받은 대표 메뉴 원문(`detailIntro2`)이고 나머지는 `null`입니다.
- 식단(할랄·채식·비건·알레르기·글루텐), 영업시간, 휴무일, 가격, 평점, 순위는 데이터에 없습니다. 주장하지 말고 가게에 확인하라고 안내하십시오. `menu_raw`로 식단을 추측하지 마십시오.
- 도구: `get_restaurants(place_id=None, station=None, radius_m=500, limit=10)` (`backend/app/tools/restaurants.py`). `place_id`와 `station` 중 하나는 필수이고 둘 다 주면 `place_id`가 우선입니다. `radius_m`은 수집 반경(500m)까지입니다. 거리는 직선거리, `walk_min`은 추정입니다.

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
- `rain_alternatives` 후보에서는 대형 상업·유료 시설 3곳(`sea-life-busan`, `busan-x-the-sky`, `shinsegae-centum-city`)을 뺍니다(`build_curation.RAIN_EXCLUDED`). 비 올 때마다 유료 수족관·전망대·백화점만 추천되는 것을 막기 위해서입니다. 이 장소 자체의 항목과 `crowd_alternatives`는 그대로입니다.
- 사람이 고친 항목은 `curation_overrides.json`에 두면 다시 만들 때 덮어쓰고 `source`가 `"manual"`이 됩니다.
- 도구: `get_place_info(place_id)`. `Place` + `curation` + `hours`를 한 번에 돌려줍니다. `search_places` 결과에는 큐레이션을 넣지 않습니다.
- 대체 후보는 후보일 뿐입니다. 그 장소의 실제 혼잡·날씨는 `get_crowd`·`get_weather`로 확인하십시오.

## 장소 정보
- 한국관광공사 다국어 관광정보서비스(영문·일문·중문 번체, 중문 간체는 신청 후 사용)와 부산시 명소정보를 사용하십시오.
- 운영시간·요금·휴무일은 도구 결과에 있는 값만 쓰십시오. 없으면 모른다고 답하고 지어내지 마십시오.
- `backend/app/data/places.json`의 좌표, 다국어 이름, 가까운 역은 아직 검증하지 않은 값입니다. 공공데이터로 교체하기 전에는 사실처럼 단정하지 마십시오.

## 금지 사항
- 카카오 API 결과를 저장·캐시하지 마십시오(파일·DynamoDB·메모리 캐시 모두, 오프라인 캐시 모드 포함). 실시간 호출만 허용되며, 대중교통 경로는 `get_return_options`, 로컬 키워드 검색은 `GET /activities`에서만 호출합니다.
- 네이버 블로그·검색 결과를 수집하거나 AI로 가공하지 마십시오.
- 공공데이터 원문을 화면에 표시할 때 출처를 함께 표기하십시오. 백엔드는 출처를 `sources`에 담습니다.

## 계산과 생성의 역할 구분
- LLM 담당: 장소 선택, 이유 설명, 다국어 문장
- 코드 담당: 방문 순서·시각 계산, 이동 시간, 수치, 장소 ID 검증, Guardian 점검과 해결안 탐색
- LLM 응답에 포함된 장소 ID가 `backend/app/data/places.json`에 없으면 버리고 다시 시도하십시오.
