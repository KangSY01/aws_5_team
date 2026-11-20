import { getActivityCopy } from "./activityCopy.js";

const keys = [
  "recommend", "newCourse", "makeCourse", "stay", "areas", "interests", "options", "food",
  "transport", "lessWalking", "origin", "lodging", "automatic", "planning", "editing", "editStop",
  "clearTarget", "apply", "before", "after", "requestFailed", "noCandidate", "lockedStop",
  "stale", "demoCourse", "demoSuggestion", "sampleEvent", "closeEvent", "lodgingUnavailable",
  "catalogLimit", "schematicRoute", "pickStop", "applied", "demoAccount", "noPlaces",
];

const labels = {
  ko: ["AI 일정 추천받기","새 코스 만들기","코스 만들기","얼마나 머무르나요?","어디를 둘러보고 싶나요?","무엇을 하고 싶나요?","조건 더하기","먹거리 취향","이동수단","걷는 거리 줄이기","출발지","숙박 추천","AI에게 맡기기","코스를 만드는 중…","대체 장소를 찾는 중…","AI로 수정","수정 대상 해제","일정에 적용","기존 장소","대체 장소","요청에 실패했어요. 다시 시도해 주세요.","현재 시간과 앞뒤 동선에 맞는 장소를 찾지 못했어요.","고정된 장소는 수정할 수 없어요.","일정이 바뀌었어요. 대체안을 다시 요청해 주세요.","데모 추천","데모 대체안","샘플 행사","행사 닫기","숙박 정보가 아직 없어요.","데모 장소 데이터에는 이 조건을 확인할 정보가 없어요.","점선은 방문 순서 개략선입니다.","일정에서 AI로 수정할 장소를 선택해 주세요.","대체 장소를 일정에 적용했어요.","데모 사용자","선택한 지역에 등록된 장소가 없어요."],
  en: ["Get an AI itinerary","Create a new itinerary","Create itinerary","How long will you stay?","Where would you like to go?","What would you like to do?","More preferences","Food preferences","Transportation","Walk less","Starting point","Suggest accommodation","Let AI decide","Creating your itinerary…","Finding an alternative…","Edit with AI","Clear edit target","Apply to itinerary","Current place","Alternative","The request failed. Please try again.","No catalog place fits the time and nearby stops.","A fixed stop cannot be edited.","The itinerary changed. Request a new suggestion.","Demo itinerary","Demo suggestion","Sample event","Close event","Accommodation information is unavailable.","The demo catalog cannot verify this preference.","Dotted lines show approximate visit order.","Choose a stop to edit from your itinerary.","The alternative was applied.","Demo traveler","No places are available in the selected area."],
  ja: ["AIに旅程を提案してもらう","新しい旅程を作る","旅程を作る","滞在期間は？","どこへ行きたいですか？","何をしたいですか？","条件を追加","食の好み","移動手段","歩く距離を減らす","出発地","宿泊先を提案","AIに任せる","旅程を作成中…","代わりの場所を検索中…","AIで変更","変更対象を解除","旅程に適用","現在の場所","代わりの場所","失敗しました。もう一度お試しください。","時間と前後の訪問先に合う場所がありません。","固定された訪問先は変更できません。","旅程が変わりました。提案を再取得してください。","デモ旅程","デモ提案","サンプルイベント","イベントを閉じる","宿泊情報はありません。","デモの場所データではこの条件を確認できません。","点線はおおよその訪問順です。","旅程から変更したい場所を選んでください。","代わりの場所を適用しました。","デモ利用者","選んだ地域に登録された場所がありません。"],
  "zh-Hans": ["获取 AI 行程","创建新行程","创建行程","停留多久？","想去哪里？","想做什么？","添加条件","饮食偏好","出行方式","少走路","出发地点","推荐住宿","交给 AI","正在创建行程…","正在寻找替代地点…","用 AI 修改","清除修改目标","应用到行程","当前地点","替代地点","请求失败，请重试。","没有符合时间和前后路线的地点。","固定地点无法更改。","行程已变更，请重新获取建议。","演示行程","演示建议","示例活动","关闭活动","暂无住宿信息。","演示地点数据无法验证此条件。","虚线表示大致的游览顺序。","请在行程中选择要修改的地点。","已应用替代地点。","演示用户","所选区域暂无地点。"],
  "zh-Hant": ["取得 AI 行程","建立新行程","建立行程","停留多久？","想去哪裡？","想做什麼？","新增條件","飲食偏好","交通方式","少走路","出發地點","推薦住宿","交給 AI","正在建立行程…","正在尋找替代地點…","用 AI 修改","清除修改目標","套用至行程","目前地點","替代地點","請求失敗，請重試。","沒有符合時間和前後路線的地點。","固定地點無法更改。","行程已變更，請重新取得建議。","示範行程","示範建議","範例活動","關閉活動","暫無住宿資訊。","示範景點資料無法驗證此條件。","虛線表示大致的遊覽順序。","請在行程中選擇要修改的地點。","已套用替代地點。","示範使用者","所選區域暫無地點。"],
};

export const durationIds = ["half", "day", "overnight", "long"];
export const foodPreferenceIds = ["korean", "chinese", "japanese", "western", "southeast_asian", "indian", "busan_local", "seafood", "market_food", "dessert", "vegetarian"];
export const transportPreferenceIds = ["public_transit", "car", "walking", "any"];
export const areaIds = ["east", "center", "oldtown", "downtown", "songdo", "estuary", "geumjeong"];
const choices = {
  ko: [["반나절","하루","1박 2일","2박 이상"],["해운대·기장","광안리·수영","남포·영도","서면·전포"]],
  en: [["Half a day","One day","Two days, one night","Two nights or more"],["Haeundae · Gijang","Gwangalli · Suyeong","Nampo · Yeongdo","Seomyeon · Jeonpo"]],
  ja: [["半日","1日","1泊2日","2泊以上"],["海雲台・機張","広安里・水営","南浦・影島","西面・田浦"]],
  "zh-Hans": [["半天","一天","两天一夜","两晚或以上"],["海云台·机张","广安里·水营","南浦·影岛","西面·田浦"]],
  "zh-Hant": [["半天","一天","兩天一夜","兩晚或以上"],["海雲臺·機張","廣安里·水營","南浦·影島","西面·田浦"]],
};

const areaActions = {
  ko: ["이 지역 추가", "지역 미리보기 닫기", "지역 빼기", "지도에서 지역 고르기", "선택 완료", "취소", "지도에서 지역 변경", "지역을 고르지 않으면 AI가 추천해요."],
  en: ["Add", "Close area preview", "Remove area", "Choose areas on the map", "Done", "Cancel", "Change areas on the map", "Leave areas blank and AI will suggest where to go."],
  ja: ["このエリアを追加", "エリアの詳細を閉じる", "エリアを削除", "地図でエリアを選ぶ", "選択を完了", "キャンセル", "地図でエリアを変更", "エリアを選ばない場合は、AIがおすすめします。"],
  "zh-Hans": ["添加此区域", "关闭区域预览", "移除区域", "在地图上选择区域", "完成选择", "取消", "在地图上更改区域", "如果不选择区域，AI 会为你推荐。"],
  "zh-Hant": ["新增此區域", "關閉區域預覽", "移除區域", "在地圖上選擇區域", "完成選擇", "取消", "在地圖上變更區域", "如果不選擇區域，AI 會為你推薦。"],
};

const areaDescriptions = {
  ko: ["해운대 해변을 걷고 기장의 바닷가 사찰을 둘러보세요.", "광안리 해변과 수영의 골목에서 광안대교 전망을 즐겨보세요.", "남포의 전통시장과 영도의 항구 풍경을 한 번에 둘러보세요.", "서면의 번화한 거리와 전포의 조용한 카페 골목을 걸어보세요."],
  en: ["Walk along Haeundae Beach and explore Gijang’s seaside temples.", "Enjoy Gwangan Bridge views from the beach and wander Suyeong’s local streets.", "Explore Nampo’s traditional markets and take in the harbor views on Yeongdo.", "Browse Seomyeon’s busy shopping streets and the quieter café lanes of Jeonpo."],
  ja: ["海雲台のビーチを歩き、機張の海辺の寺を訪ねましょう。", "広安里の砂浜から広安大橋を眺め、水営の路地を散策しましょう。", "南浦の伝統市場を巡り、影島から港の風景を楽しみましょう。", "西面のにぎやかな通りと田浦のカフェが並ぶ路地を歩きましょう。"],
  "zh-Hans": ["漫步海云台海滩，探访机张的海边寺庙。", "从广安里海滩欣赏广安大桥，再到水营的街巷走走。", "逛逛南浦的传统市场，再到影岛欣赏港口风景。", "逛逛西面的繁华商街，再去田浦的咖啡小巷。"],
  "zh-Hant": ["漫步海雲臺海灘，探訪機張的海邊寺廟。", "從廣安里海灘欣賞廣安大橋，再到水營的街巷走走。", "逛逛南浦的傳統市場，再到影島欣賞港口風景。", "逛逛西面的繁華商街，再去田浦的咖啡小巷。"],
};

const additionalAreas = {
  ko: [
    ["송도·감천", "다대포·을숙도", "동래·금정"],
    ["감천의 알록달록한 골목을 걷고 송도 해변과 해상케이블카를 즐겨보세요.", "다대포에서 노을을 보고 을숙도에서 낙동강 하구의 자연을 만나보세요.", "동래 온천장과 금정산성에서 부산의 역사를 만나보세요."],
    "선택한 지역에 등록된 장소가 적어 짧은 코스로 만들었어요.",
  ],
  en: [
    ["Songdo · Gamcheon", "Dadaepo · Eulsukdo", "Dongnae · Geumjeong"],
    ["Wander Gamcheon’s colorful lanes, then explore Songdo Beach and its cable car.", "Catch the sunset at Dadaepo and explore the wetlands on Eulsukdo Island.", "Discover Busan’s history around Dongnae’s hot springs and Geumjeong Fortress."],
    "This itinerary is shorter because the selected areas have limited places in the demo catalog.",
  ],
  ja: [
    ["松島・甘川", "多大浦・乙淑島", "東莱・金井"],
    ["甘川のカラフルな路地を歩き、松島のビーチと海上ケーブルカーを楽しみましょう。", "多大浦で夕日を眺め、乙淑島で洛東江河口の自然にふれましょう。", "東莱の温泉場と金井山城で釜山の歴史にふれましょう。"],
    "選んだエリアの登録スポットが少ないため、短めの旅程になりました。",
  ],
  "zh-Hans": [
    ["松岛·甘川", "多大浦·乙淑岛", "东莱·金井"],
    ["漫步甘川的彩色小巷，体验松岛海滩和海上缆车。", "在多大浦看日落，到乙淑岛探索洛东江河口湿地。", "在东莱温泉与金井山城了解釜山的历史。"],
    "所选区域的演示景点有限，因此生成了较短的行程。",
  ],
  "zh-Hant": [
    ["松島·甘川", "多大浦·乙淑島", "東萊·金井"],
    ["漫步甘川的彩色巷弄，體驗松島海灘和海上纜車。", "在多大浦看日落，到乙淑島探索洛東江河口濕地。", "在東萊溫泉與金井山城了解釜山的歷史。"],
    "所選區域的示範景點有限，因此產生了較短的行程。",
  ],
};

const selectionStatus = {
  ko: "추가됨",
  en: "Added",
  ja: "追加済み",
  "zh-Hans": "已添加",
  "zh-Hant": "已新增",
};

const answerCopy = {
  ko: ["필수", "선택", "여행 기간을 선택해 주세요."],
  en: ["Required", "Optional", "Choose how long you’ll stay."],
  ja: ["必須", "任意", "滞在期間を選んでください。"],
  "zh-Hans": ["必填", "选填", "请选择停留时间。"],
  "zh-Hant": ["必填", "選填", "請選擇停留時間。"],
};

const foodTransportCopy = {
  ko: [["한식","중식","일식","양식","동남아식","인도식","부산 향토 음식","해산물","시장 먹거리","디저트","채식"],["대중교통","차량","도보 위주","상관없음"],["먹거리 취향 직접 추가","먹거리 취향이나 피할 음식 입력","추가","직접 추가한 먹거리 취향 삭제","이미 목록에 있는 취향이에요."]],
  en: [["Korean","Chinese","Japanese","Western","Southeast Asian","Indian","Local Busan food","Seafood","Market food","Desserts","Vegetarian"],["Public transit","Car","Mostly walking","No preference"],["Add a food preference","Enter a preference or food to avoid","Add","Remove custom food preference","This preference is already in the list."]],
  ja: [["韓国料理","中華料理","日本料理","洋食","東南アジア料理","インド料理","釜山の郷土料理","海鮮","市場グルメ","デザート","菜食"],["公共交通","車","徒歩中心","こだわらない"],["食の好みを追加","好みや避けたい食べ物を入力","追加","追加した食の好みを削除","この好みは登録済みです。"]],
  "zh-Hans": [["韩餐","中餐","日料","西餐","东南亚菜","印度菜","釜山乡土美食","海鲜","市场小吃","甜点","素食"],["公共交通","汽车","以步行为主","无偏好"],["添加饮食偏好","输入偏好或要避免的食物","添加","移除自定义饮食偏好","该偏好已在列表中。"]],
  "zh-Hant": [["韓式料理","中式料理","日式料理","西式料理","東南亞料理","印度料理","釜山鄉土美食","海鮮","市場小吃","甜點","素食"],["大眾運輸","汽車","以步行為主","無偏好"],["新增飲食偏好","輸入偏好或要避免的食物","新增","移除自訂飲食偏好","該偏好已在清單中。"]],
};

const emptyRecommendationCopy = {
  ko: "지금 조건으로 일정을 만들지 못했어요. 지역이나 활동을 줄이거나, 기간만 남겨 다시 시도해 주세요.",
  en: "We couldn't create an itinerary with these preferences. Try fewer areas or activities, or leave only the duration.",
  ja: "この条件では旅程を作成できませんでした。エリアやアクティビティを減らすか、滞在期間だけでお試しください。",
  "zh-Hans": "未能按当前偏好创建行程。请减少地区或活动，或仅保留停留时长后重试。",
  "zh-Hant": "未能依目前偏好建立行程。請減少地區或活動，或只保留停留時間後再試。",
};

const planServerErrors = {
  ko: { generation: "서버에서 일정을 만들지 못했어요. 잠시 후 다시 시도해 주세요.", lookup: "서버에서 저장된 일정을 불러오지 못했어요." },
  en: { generation: "The server couldn't create the itinerary. Try again shortly.", lookup: "The server couldn't load the saved itinerary." },
  ja: { generation: "サーバーで旅程を作成できませんでした。少し時間をおいてお試しください。", lookup: "保存された旅程を読み込めませんでした。" },
  "zh-Hans": { generation: "服务器未能创建行程，请稍后重试。", lookup: "服务器未能读取已保存的行程。" },
  "zh-Hant": { generation: "伺服器未能建立行程，請稍後再試。", lookup: "伺服器未能讀取已儲存的行程。" },
};

const chatOutcomeCopy = {
  ko: ["요청한 변경을 반영하지 못했어요. 기존 일정은 그대로예요.", "일정에 변경 사항을 반영했어요. 일정 탭에서 확인할 수 있어요.", "{place}(으)로 방문 장소를 바꿨어요."],
  en: ["The requested change couldn't be made. Your itinerary is unchanged.", "Your itinerary was updated. See the itinerary tab for details.", "The stop was replaced with {place}."],
  ja: ["リクエストを反映できませんでした。旅程は変更されていません。", "旅程を更新しました。日程タブで確認できます。", "訪問先を{place}に変更しました。"],
  "zh-Hans": ["无法完成请求的更改，原行程保持不变。", "已更新行程，请在行程页面查看。", "已将该地点更换为{place}。"],
  "zh-Hant": ["無法完成要求的變更，原行程保持不變。", "已更新行程，請在行程頁面查看。", "已將該地點更換為{place}。"],
};

const generalChatDemo = {
  ko: "데모에서는 저장된 명소 소개를 볼 수 있어요. 광안대교나 태종대에 대해 물어보세요. 그 밖의 질문에 답하려면 AI 서버 연결이 필요해요.",
  en: "The demo can share saved landmark descriptions. Ask about Gwangan Bridge or Taejongdae. Other questions need a connection to the AI server.",
  ja: "デモでは登録済みの名所を紹介できます。広安大橋や太宗台について聞いてみてください。その他の質問にはAIサーバーへの接続が必要です。",
  "zh-Hans": "演示版可以介绍已收录的地标。试着问问广安大桥或太宗台。其他问题需要连接 AI 服务。",
  "zh-Hant": "示範版可以介紹已收錄的地標。試著問問廣安大橋或太宗臺。其他問題需要連接 AI 服務。",
};

const addNeedsItinerary = {
  ko: "추가할 일정이 아직 없어요. 일정 탭에서 코스를 먼저 만들어 주세요.",
  en: "There’s no itinerary to add to yet. Create one in the itinerary tab first.",
  ja: "追加先の旅程がありません。日程タブで旅程を作ってください。",
  "zh-Hans": "还没有可以添加的行程。请先在行程页面创建行程。",
  "zh-Hant": "還沒有可以新增的行程。請先在行程頁面建立行程。",
};

const additionTiming = {
  ko: "기존 일정을 유지하면 요청한 시간에 이동 여유 30분과 선택한 방문 시간을 확보할 수 없어요.",
  en: "The requested time doesn’t leave room for a 30-minute travel buffer and the selected visit duration around your existing stops.",
  ja: "既存の予定を維持すると、ご希望の時刻には移動30分と選んだ滞在時間を確保できません。",
  "zh-Hans": "在保留原行程的情况下，请求的时间无法留出 30 分钟交通缓冲和 所选游览时长。",
  "zh-Hant": "在保留原行程的情況下，指定時段無法預留 30 分鐘交通緩衝及 所選遊覽時長。",
};

const placeCardLabels = {
  ko: ["장소 추천", "몇 시부터 몇 시까지 일정에 넣을까요?", "시작 시간", "종료 시간", "확인하고 일정에 추가", "일정에 추가했어요.", "다른 가능한 시간을 입력했어요. 확인 전에 바꿀 수 있어요.", "장소 자세히 보기", "종료 시간은 시작 시간보다 늦어야 해요."],
  en: ["Suggested places", "What time should this visit start and end?", "Start time", "End time", "Confirm and add to itinerary", "Added to your itinerary.", "A different available time is shown. You can change it before confirming.", "Place details", "End time must be after start time."],
  ja: ["おすすめの場所", "何時から何時まで旅程に入れますか？", "開始時刻", "終了時刻", "確認して旅程に追加", "旅程に追加しました。", "別の空き時間を表示しています。確認前に変更できます。", "場所の詳細", "終了時刻は開始時刻より後にしてください。"],
  "zh-Hans": ["推荐地点", "想把这次到访安排在几点到几点？", "开始时间", "结束时间", "确认并添加到行程", "已添加到行程。", "已显示另一个可用时段，确认前可以修改。", "地点详情", "结束时间必须晚于开始时间。"],
  "zh-Hant": ["推薦地點", "想把這次造訪安排在幾點到幾點？", "開始時間", "結束時間", "確認並新增到行程", "已新增到行程。", "已顯示另一個可用時段，確認前可以修改。", "地點詳情", "結束時間必須晚於開始時間。"],
};

const placeRecommendationCopy = {
  ko: ["추천 이유", "채팅에서 요청하신 장소예요.", "요청하신 카페를 찾았어요.", "요청하신 공원 유형에 맞아요.", "요청하신 해변 유형에 맞아요."],
  en: ["Why this place", "This is the place you asked about.", "This café matches your request.", "This park matches your request.", "This beach matches your request."],
  ja: ["おすすめの理由", "チャットで指定された場所です。", "ご希望に合うカフェです。", "ご希望に合う公園です。", "ご希望に合うビーチです。"],
  "zh-Hans": ["推荐理由", "这是你在聊天中提到的地点。", "这家咖啡馆符合你的需求。", "这座公园符合你的需求。", "这片海滩符合你的需求。"],
  "zh-Hant": ["推薦理由", "這是你在聊天中提到的地點。", "這家咖啡館符合你的需求。", "這座公園符合你的需求。", "這片海灘符合你的需求。"],
};

const activitySearchCopy = {
  ko: ["조건에 맞는 놀거리를 찾지 못했어요. 다른 지역이나 유형으로 검색해 보세요.", "지금은 놀거리 정보를 불러올 수 없어요. 잠시 후 다시 시도해 주세요."],
  en: ["No activities matched. Try a different area or type.", "Activity search is unavailable. Please try again shortly."],
  ja: ["条件に合う体験が見つかりませんでした。別のエリアや種類でお試しください。", "現在、体験を検索できません。しばらくしてからお試しください。"],
  "zh-Hans": ["没有找到符合条件的活动。请试试其他地区或类型。", "暂时无法搜索活动，请稍后再试。"],
  "zh-Hant": ["找不到符合條件的活動。請試試其他地區或類型。", "暫時無法搜尋活動，請稍後再試。"],
};

const placeStationLabel = {
  ko: "가까운 역", en: "Nearest station", ja: "最寄り駅",
  "zh-Hans": "最近车站", "zh-Hant": "最近車站",
};

export function getPlannerCopy(language) {
  const [durations, areasList] = choices[language];
  const [chatPlanUnchanged, chatPlanUpdated, chatStopReplaced] = chatOutcomeCopy[language];
  const [searchEmpty, searchUnavailable] = activitySearchCopy[language];
  const [reasonLabel, name, cafe, park, beach] = placeRecommendationCopy[language];
  const [results, prompt, start, end, confirm, added, adjusted, details, invalidEnd] = placeCardLabels[language];
  const [addArea, closeArea, removeArea, showAreas, doneAreas, cancelAreas, changeAreas, noAreaSelection] = areaActions[language];
  const [extraNames, extraDescriptions, limitedPlaces] = additionalAreas[language];
  const areaAdded = selectionStatus[language];
  const [requiredAnswer, optionalAnswer, durationRequired] = answerCopy[language];
  const [food, transport, editor] = foodTransportCopy[language];
  const [openCustom, customLabel, addCustom, removeCustom, duplicate] = editor;
  const doneAreasLabel = (total) => total
    ? `${doneAreas} · ${new Intl.NumberFormat(language).format(total)}`
    : doneAreas;
  const text = Object.fromEntries(keys.map((key, i) => [key, labels[language][i]]));
  return { ...text,
    durations, areasList: [...areasList, ...extraNames], areaDescriptions: [...areaDescriptions[language], ...extraDescriptions],
    activityCopy: getActivityCopy(language), addArea, areaAdded, closeArea, removeArea, showAreas, doneAreasLabel, cancelAreas, limitedPlaces,
    planServerError: planServerErrors[language],
    generalChatDemo: generalChatDemo[language],
    placeCards: { results, prompt, start, end, confirm, added, adjusted, details, invalidEnd, nearestStation: placeStationLabel[language],
      searchEmpty, searchUnavailable, reasonLabel, reasons: { name, cafe, park, beach }, noItinerary: addNeedsItinerary[language], stale: text.stale },
    additionNoTime: additionTiming[language],
    chatPlanUnchanged, chatPlanUpdated, chatStopReplaced: (place) => chatStopReplaced.replace("{place}", () => place),
    emptyRecommendation: emptyRecommendationCopy[language],
    requiredAnswer, optionalAnswer, durationRequired, changeAreas, noAreaSelection,
    foodLabels: Object.fromEntries(foodPreferenceIds.map((id, index) => [id, food[index]])),
    transportLabels: Object.fromEntries(transportPreferenceIds.map((id, index) => [id, transport[index]])),
    foodEditor: { openCustom, customLabel, addCustom, removeCustom, duplicate } };
}
