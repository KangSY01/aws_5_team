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
export const areaIds = ["east", "center", "oldtown", "downtown"];
export const activityIds = ["sea", "market", "cafe", "culture", "active", "night"];
const choices = {
  ko: [["반나절","하루","1박 2일","2박 이상"],["해운대·기장","광안리·수영","남포·영도","서면·전포"],["해변과 해안 사찰","바다와 광안대교","전통시장과 항구","도심 골목과 카페"],["바다 산책","시장 구경","카페","전시·문화","액티비티","야경"]],
  en: [["Half a day","One day","Two days, one night","Two nights or more"],["Haeundae · Gijang","Gwangalli · Suyeong","Nampo · Yeongdo","Seomyeon · Jeonpo"],["Beaches and seaside temples","The beach and Gwangan Bridge","Traditional markets and harbor","Downtown alleys and cafés"],["Seaside walks","Markets","Cafés","Arts and culture","Activities","Night views"]],
  ja: [["半日","1日","1泊2日","2泊以上"],["海雲台・機張","広安里・水営","南浦・影島","西面・田浦"],["海辺と海岸の寺","ビーチと広安大橋","市場と港","街の路地とカフェ"],["海辺の散歩","市場巡り","カフェ","展示・文化","アクティビティ","夜景"]],
  "zh-Hans": [["半天","一天","两天一夜","两晚或以上"],["海云台·机张","广安里·水营","南浦·影岛","西面·田浦"],["海滩与海边寺庙","海滩与广安大桥","传统市场与港口","市区小巷与咖啡馆"],["海边散步","逛市场","咖啡馆","展览文化","户外活动","夜景"]],
  "zh-Hant": [["半天","一天","兩天一夜","兩晚或以上"],["海雲臺·機張","廣安里·水營","南浦·影島","西面·田浦"],["海灘與海邊寺廟","海灘與廣安大橋","傳統市場與港口","市區小巷與咖啡館"],["海邊散步","逛市場","咖啡館","展覽文化","戶外活動","夜景"]],
};

export function getPlannerCopy(language) {
  const [durations, areasList, areaDetails, activities] = choices[language];
  return { ...Object.fromEntries(keys.map((key, i) => [key, labels[language][i]])), durations, areasList, areaDetails, activities };
}
