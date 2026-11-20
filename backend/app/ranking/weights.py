"""랭킹 가중치와 기준값. 리허설 전에 고정한다(데모 결과가 바뀌지 않게). LLM 미사용.

값은 팀이 정한 규칙이며 데이터로 학습한 값이 아니다.
"""

# ---------- 장소 점수 (score_place) ----------
# 항목별 점수는 0~1 이고, 가중합을 0~100 으로 맞춘다.
PLACE_WEIGHTS = {
    "interest": 3.0,  # 프로필 관심사와 큐레이션 태그 겹침
    "crowd": 3.0,  # 그날 혼잡 (Guardian 혼잡 규칙과 같은 판단)
    "travel": 2.0,  # 이전 장소에서 걸리는 시간
    "weather": 2.0,  # 체류 시간대 비 (실내 가점)
    "foreigner": 1.0,  # 다국어 관광정보 제공 언어 수 (curation.foreigner_friendly)
    "dispersal": 1.0,  # 원도심·서부산, 대표 명소가 아닌 곳 가점
}

NEUTRAL = 0.5  # 판단할 데이터가 없을 때의 항목 점수 (가점도 감점도 하지 않음)

# Guardian 심각도 → 점수. 문제 없음(None)은 1.0
SEVERITY_SCORE = {None: 1.0, "low": 0.75, "medium": 0.4, "high": 0.0}

TRAVEL_SCORE_MAX_MIN = 60  # 이동 시간 점수: 0분 = 1.0, 이 값 이상 = 0.0 (선형)

FOREIGNER_FRIENDLY_MAX = 3  # curation.foreigner_friendly 최댓값 (영어·일본어·중국어)

# 분산 보너스 = 원도심·서부산이면 DISPERSAL_WEST + 대표 명소가 아니면 DISPERSAL_NOT_LANDMARK (합 1.0).
# 월 방문자 데이터가 저장소에 없어서 권역 규칙과 대표 명소 목록으로 대신한다.
# 권역: 경도가 이 값보다 작으면(서쪽) 원도심·서부산으로 본다. 행정 구역 경계가 아닌 근사다.
# 129.07 은 범어사(129.070)·태종대(129.080)·국립해양박물관(129.080) 바로 서쪽이다.
DISPERSAL_MAX_LNG = 129.07
DISPERSAL_WEST = 0.5
DISPERSAL_NOT_LANDMARK = 0.5

# 대표 명소: 처음 오는 관광객이 대부분 들르는 곳. 팀이 정한 목록이며 방문자 통계로 고른 값이 아니다.
# curation.json 에는 "덜 알려진 장소"를 나타내는 필드가 없어서 여기 둔다. place_id 는 places.json 기준.
LANDMARKS = frozenset({
    "haeundae-beach",
    "gwangalli-beach",
    "gamcheon-village",
    "haedong-yonggungsa",
    "jagalchi-market",
    "gukje-market",
    "taejongdae",
})

# 대형 상업시설: 대표 명소가 아니어도 분산 보너스(DISPERSAL_NOT_LANDMARK)를 주지 않는다.
# 대형 시설로 몰린 소비를 중소 상권으로 옮기는 목적과 반대이기 때문. place_id 는 places.json 기준.
LARGE_COMMERCIAL = frozenset({
    "shinsegae-centum-city",
    "lotte-outlet-dongbusan",
    "lotte-world-busan",
    "the-bay-101",
    "busan-x-the-sky",
    "sea-life-busan",
})

# ---------- 방문 순서 점수 (rank_orders) ----------
# 순서 점수 = -(이동 분 × W_TRAVEL) - (비 노출 × W_RAIN) + (고정 일정 앞 여유 분, 상한 적용 × W_SLACK). 높을수록 좋다.
ORDER_W_TRAVEL = 1.0  # 총 이동 시간 1분당
ORDER_W_RAIN = 30.0  # 실외 Stop 의 비 심각도 점수 1점당 (medium=1, high=2)
ORDER_W_SLACK = 0.5  # 고정 일정 앞 여유 1분당
ORDER_SLACK_CAP_MIN = 60  # 여유는 이 값까지만 가점 (너무 일찍 도착하는 순서를 고르지 않게)

RAIN_POINTS = {"medium": 1, "high": 2}

ROUND_MIN = 10  # 다음 Stop 시작 시각을 이 단위로 올림 (tools/schedule.py 와 같은 규칙)
FALLBACK_TRAVEL_MIN = 30  # 이동 시간을 모를 때 (tools/schedule.py 와 같은 값)
MAX_ORDER_PLACES = 7  # 이보다 장소가 많으면 모든 순서를 채점하지 않는다 (6! = 720 순서까지)

# ---------- 귀가 경로 점수 (rank_routes, 장면 7) ----------
# 비용(분 환산) = 이동 분 × W_TRAVEL + 일찍 떠나는 분 × W_EARLY + 늦게 출발해 기다리는 분 × W_WAIT
#              + 도보 분 × W_WALK + 경고·혼잡 벌점. 점수 = -비용. 높을수록 좋다.
ROUTE_W_TRAVEL = 1.0  # 출발 후 도착역까지 1분당 (baseline.minutes + extra_min)
ROUTE_W_EARLY = 1.0  # 계획 출발(행사 종료)보다 일찍 떠나는 1분당. 행사를 덜 본다
ROUTE_W_WAIT = 0.5  # 계획 출발보다 늦게 떠나는 1분당. 근처에서 쉬며 기다릴 수 있어 이동보다 가볍게 본다
ROUTE_W_WALK = 0.5  # 다른 역까지 걷는 1분당 (이동 분에 이미 들어 있고, 밤길 도보 부담을 더한다)
ROUTE_PENALTY = {
    "crowded": 30.0,  # avoids_congestion 이 false
    "last_train_unknown": 20.0,  # 막차 표가 없어 탈 수 있는지 모름
}
ROUTE_EXCLUDE_WARNINGS = frozenset({"last_train_missed"})  # 막차를 놓치는 안은 후보에서 뺀다
