"""사용자에게 직접 보여 주는 고정 문장. 모델이 쓰지 않는 안내문(일정을 만들지 못했을 때 등)과 출처 제목.

다국어 검수는 D 담당이 한다 (docs/prompt-review.md). plan_invalid·plan_changed·plan_created·no_valid_places 는 D 가 검수한 문장이다.
"""

from app.models.plan import Language

LANGUAGES: tuple[Language, ...] = ("en", "ja", "zh-Hans", "zh-Hant")

# 장소 이름을 나열할 때의 구분자. 일본어·중국어는 나열 쉼표(、)를 쓴다
LIST_SEPARATORS: dict[Language, str] = {"en": ", ", "ja": "、", "zh-Hans": "、", "zh-Hant": "、"}

MESSAGES: dict[str, dict[Language, str]] = {
    # build_plan 이 PlanBuildError 로 알려 주는 사유 (app/tools/schedule.py)
    "no_valid_places": {
        "en": "I couldn't find suitable places to build an itinerary. Tell me what you enjoy (for example food, the sea or culture) and I'll try again.",
        "ja": "旅程に合う場所が見つかりませんでした。興味のあること（グルメ、海、文化など）を教えてください。もう一度探します。",
        "zh-Hans": "没有找到适合安排行程的地点。请告诉我您的兴趣（例如美食、海边或文化），我会再试一次。",
        "zh-Hant": "沒有找到適合安排行程的地點。請告訴我您的興趣（例如美食、海邊或文化），我會再試一次。",
    },
    "invalid_date": {
        "en": "I couldn't understand the date. Please give it like 2026-11-28.",
        "ja": "日付を読み取れませんでした。2026-11-28 のように教えてください。",
        "zh-Hans": "无法识别日期。请按 2026-11-28 的格式告诉我。",
        "zh-Hant": "無法辨識日期。請依 2026-11-28 的格式告訴我。",
    },
    "invalid_start": {
        "en": "I couldn't understand the start time. Please give it like 10:00.",
        "ja": "開始時刻を読み取れませんでした。10:00 のように教えてください。",
        "zh-Hans": "无法识别开始时间。请按 10:00 的格式告诉我。",
        "zh-Hant": "無法辨識開始時間。請依 10:00 的格式告訴我。",
    },
    "data_unavailable": {
        "en": "The place data is temporarily unavailable. Please try again in a moment.",
        "ja": "場所のデータを一時的に読み込めません。しばらくしてからもう一度お試しください。",
        "zh-Hans": "暂时无法读取地点数据，请稍后再试。",
        "zh-Hant": "暫時無法讀取地點資料，請稍後再試。",
    },
    # 만든 일정·바꾼 일정이 검증(시간 겹침 등)을 통과하지 못해 저장하지 않았을 때
    "plan_invalid": {
        "en": "I couldn't save that because the schedule would not work (for example, stops would overlap). Nothing was changed.",
        "ja": "時間が重なるなどスケジュールが成り立たないため、保存できませんでした。何も変更していません。",
        "zh-Hans": "该安排无法成立（例如时间重叠），因此未保存，没有任何更改。",
        "zh-Hant": "該安排無法成立（例如時間重疊），因此未儲存，沒有任何變更。",
    },
    # 모델이 답변을 만들지 못했고 적용할 변경도 없을 때
    "incomplete": {
        "en": "I couldn't finish that request. Please try again with a simpler request.",
        "ja": "リクエストを最後まで処理できませんでした。もう少しシンプルな内容でもう一度お試しください。",
        "zh-Hans": "未能完成该请求。请换一种更简单的说法再试一次。",
        "zh-Hant": "未能完成該請求。請換一種更簡單的說法再試一次。",
    },
    # 모델이 답변 문장을 만들지 못했지만 일정은 만들어졌거나 바뀌었을 때 (도구 호출 한도 등)
    "plan_created": {
        "en": "I made a {count}-stop plan for {date}: {places}.",
        "ja": "{date}の旅程（{count}か所）を作りました：{places}。",
        "zh-Hans": "已为 {date} 安排了 {count} 个地点的行程：{places}。",
        "zh-Hant": "已為 {date} 安排了 {count} 個地點的行程：{places}。",
    },
    "plan_changed": {
        "en": "I updated {count} stop(s) in your itinerary. Locked stops were not changed.",
        "ja": "旅程の{count}か所を更新しました。固定された訪問先は変更していません。",
        "zh-Hans": "已更新行程中的 {count} 个地点。固定地点未更改。",
        "zh-Hant": "已更新行程中的 {count} 個地點。固定地點未更改。",
    },
    # sources 의 title (장소 이름이 title 인 출처는 장소 이름을 쓴다)
    "source_weather": {
        "en": "Busan short-term weather forecast",
        "ja": "釜山の短期天気予報",
        "zh-Hans": "釜山短期天气预报",
        "zh-Hant": "釜山短期天氣預報",
    },
    "source_events": {
        "en": "Busan events ({date})",
        "ja": "釜山のイベント（{date}）",
        "zh-Hans": "釜山活动（{date}）",
        "zh-Hant": "釜山活動（{date}）",
    },
    "source_travel": {
        "en": "Travel time estimate: {origin} → {destination}",
        "ja": "移動時間の目安：{origin} → {destination}",
        "zh-Hans": "交通时间估算：{origin} → {destination}",
        "zh-Hant": "交通時間估算：{origin} → {destination}",
    },
}

# PlanBuildError 코드 중 사용자에게 안내문을 주는 것. 모르는 코드는 no_valid_places 가 아니라 incomplete 로 안내한다
BUILD_ERROR_KEYS = frozenset({"no_valid_places", "invalid_date", "invalid_start", "data_unavailable"})


def message(key: str, language: Language, **values: object) -> str:
    return MESSAGES[key][language].format(**values)
