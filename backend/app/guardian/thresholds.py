"""Guardian 점검·해결안 기준값. 리허설 전에 데모 데이터로 맞추고 고정한다.

값의 근거와 뜻은 .kiro/specs/schedule-guardian/design.md 의 "기준값" 표를 따른다.
여기 값을 바꾸면 그 표도 함께 고친다.
"""

from app.models.plan import Severity

# 혼잡 (집중률은 장소마다 자기 최고 시기=100인 상대값. 장소끼리 비교하지 않는다)
CROWD_MEDIUM_RATE = 85  # 집중률이 이 값 이상이면 medium
CROWD_HIGH_RATE = 95  # 집중률이 이 값 이상이고 주말이면 high

# 집중률 데이터에 없는 장소. 요일 규칙으로 판단한다 (places.json 에 있는 ID만, data-rules.md 「혼잡도」 목록)
WEEKDAY_RULE_PLACES = frozenset({
    "gamcheon-village",
    "haedong-yonggungsa",
    "huinnyeoul-village",
    "haeridan-gil",
    "blueline-park",
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
