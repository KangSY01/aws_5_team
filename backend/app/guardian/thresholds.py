"""Guardian 점검·해결안 기준값. 리허설 전에 데모 데이터로 맞추고 고정한다.

값의 근거와 뜻은 .kiro/specs/schedule-guardian/design.md 의 "기준값" 표를 따른다.
여기 값을 바꾸면 그 표도 함께 고친다.
"""

from app.models.plan import Severity

# 혼잡 (집중률은 장소마다 자기 최고 시기=100인 상대값. 장소끼리 비교하지 않는다)
# 받아 둔 30일(11/18~12/17) 안에서는 토요일이 대부분 장소의 최고 시기라 85 기준이면 토요일 일정 거의 전부가 걸린다.
# 11/28(토) 21곳 중 85 이상 17곳, 95 이상 7곳, 98 이상 2곳 → 95/98 (데모 장면 1 배지 3개)
CROWD_MEDIUM_RATE = 95  # 집중률이 이 값 이상이면 medium
CROWD_HIGH_RATE = 98  # 집중률이 이 값 이상이고 주말이면 high

# 집중률 데이터에 없는 장소. 요일 규칙으로 판단한다 (places.json 에 있는 ID만, data-rules.md 「혼잡도」 목록)
WEEKDAY_RULE_PLACES = frozenset({
    "gamcheon-village",
    "busan-tower",
    "haedong-yonggungsa",
    "shinsegae-centum-city",
    "haeridan-gil",
    "blueline-park",
    "busan-x-the-sky",
    "busan-cinema-center",
    "lotte-outlet-dongbusan",
    "huinnyeoul-village",
    "busan-modern-history-museum",
    "choryang-ibagu-gil",
    "haeundae-rodeo-street",
    "busan-cinema-street",
})
# 요일 규칙 심각도. 키는 datetime.weekday() 값 (5=토, 6=일). 평일은 문제 없음
WEEKDAY_RULE_SEVERITY: dict[int, Severity] = {5: "medium", 6: "low"}

# 비
RAIN_POP_MEDIUM = 60  # 체류 시간대 최대 강수확률(%)이 이 값 이상이면 medium
RAIN_PTY_HIGH_RATIO = 0.5  # 체류 시간의 이 비율 이상에 강수가 있으면 high

# 이동
TRANSFER_BUFFER_MIN = 10  # 이동 여유(분). 미만이면 medium, 0 미만이면 high

# 해결안 탐색
MIN_DWELL_MIN = 45  # 체류 시간 축소 하한(분)
SHIFT_STEPS_MIN = (30, 60, 90)  # move_time 시도 폭(분)
REPLACE_MAX_EXTRA_MIN = 40  # replace·reorder 이동 시간 증가 상한(분). 데모 장면 2(해운대→송정 +37분)에 맞춰 30→40
MAX_REPAIRS = 3  # Issue 하나당 돌려줄 해결안 수

# 혼잡 교체의 도보권 상권 후보: 붐비는 장소에서 이 시간 안의 시장·거리를 category 가 달라도 후보에 넣고 먼저 보인다.
# 대형 명소에 몰린 방문객을 근처 중소 상권으로 분산하는 목적 (데모 장면 2: 해운대해수욕장 → 해운대시장 도보 6분).
LOCAL_COMMERCE_CATEGORIES = frozenset({"market", "street"})
LOCAL_COMMERCE_MAX_MIN = 15

# 대형 상업시설: replace 후보로 쓰지 않는다 (비·혼잡 모두). 대형 시설로 몰린 소비를 중소 상권으로 옮기는 목적과 반대.
# 랭킹 분산 보너스 제외(app/ranking/weights.py)도 이 목록을 쓴다. place_id 는 places.json 기준.
LARGE_COMMERCIAL = frozenset({
    "shinsegae-centum-city",
    "lotte-outlet-dongbusan",
    "lotte-world-busan",
    "the-bay-101",
    "busan-x-the-sky",
    "sea-life-busan",
})
