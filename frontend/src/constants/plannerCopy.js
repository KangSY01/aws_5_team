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

export function getPlannerCopy(language) {
  const [durations, areasList] = choices[language];
  const [addArea, closeArea, removeArea, showAreas, doneAreas, cancelAreas, changeAreas, noAreaSelection] = areaActions[language];
  const [extraNames, extraDescriptions, limitedPlaces] = additionalAreas[language];
  const areaAdded = selectionStatus[language];
  const [requiredAnswer, optionalAnswer, durationRequired] = answerCopy[language];
  const [food, transport, editor] = foodTransportCopy[language];
  const [openCustom, customLabel, addCustom, removeCustom, duplicate] = editor;
  const doneAreasLabel = (total) => total
    ? `${doneAreas} · ${new Intl.NumberFormat(language).format(total)}`
    : doneAreas;
  return { ...Object.fromEntries(keys.map((key, i) => [key, labels[language][i]])),
    durations, areasList: [...areasList, ...extraNames], areaDescriptions: [...areaDescriptions[language], ...extraDescriptions],
    activityCopy: getActivityCopy(language), addArea, areaAdded, closeArea, removeArea, showAreas, doneAreasLabel, cancelAreas, limitedPlaces,
    requiredAnswer, optionalAnswer, durationRequired, changeAreas, noAreaSelection,
    foodLabels: Object.fromEntries(foodPreferenceIds.map((id, index) => [id, food[index]])),
    transportLabels: Object.fromEntries(transportPreferenceIds.map((id, index) => [id, transport[index]])),
    foodEditor: { openCustom, customLabel, addCustom, removeCustom, duplicate } };
}
