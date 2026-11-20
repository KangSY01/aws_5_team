import { activityGroups } from "../lib/activityPreferences.js";

const ids = activityGroups.flatMap(([, activities]) => activities);
const labels = {
  ko: [["바다·자연","시장·카페","문화·골목","체험·쇼핑","풍경·저녁"],
    ["해변 산책","해안 산책로","섬·습지 탐방","가벼운 등산","전통시장","길거리 음식","오션뷰 카페","로컬 카페","미술관·전시","역사·유적","사찰","벽화마을","서핑·수상 체험","케이블카","체험 공방","쇼핑","노을 명소","야경","사진 명소","공연·축제"]],
  en: [["Sea & nature","Markets & cafés","Culture & neighborhoods","Experiences & shopping","Scenery & evenings"],
    ["Beach walks","Coastal trails","Islands & wetlands","Easy hikes","Traditional markets","Street food","Ocean-view cafés","Local cafés","Art museums & exhibitions","History & heritage","Temples","Mural villages","Surfing & water activities","Cable cars","Craft workshops","Shopping","Sunset spots","Night views","Photo spots","Performances & festivals"]],
  ja: [["海・自然","市場・カフェ","文化・路地","体験・ショッピング","風景・夜"],
    ["ビーチ散歩","海岸の遊歩道","島・湿地めぐり","軽いハイキング","伝統市場","屋台グルメ","海が見えるカフェ","地元のカフェ","美術館・展示","歴史・史跡","寺院","壁画村","サーフィン・水上体験","ケーブルカー","工房体験","ショッピング","夕日の名所","夜景","撮影スポット","公演・祭り"]],
  "zh-Hans": [["海滨与自然","市场与咖啡馆","文化与街巷","体验与购物","风景与夜晚"],
    ["海滩散步","海岸步道","海岛与湿地探索","轻松徒步","传统市场","街头美食","海景咖啡馆","本地咖啡馆","美术馆与展览","历史与遗址","寺庙","壁画村","冲浪与水上活动","缆车","手作工坊","购物","日落景点","夜景","拍照景点","演出与节庆"]],
  "zh-Hant": [["海濱與自然","市場與咖啡館","文化與巷弄","體驗與購物","風景與夜晚"],
    ["海灘散步","海岸步道","海島與濕地探索","輕鬆健行","傳統市場","街頭美食","海景咖啡館","在地咖啡館","美術館與展覽","歷史與遺址","寺廟","壁畫村","衝浪與水上活動","纜車","手作工坊","購物","日落景點","夜景","拍照景點","表演與節慶"]],
};

export function getActivityCopy(language) {
  const [groupLabels, activityLabels] = labels[language];
  const [openCustom, customLabel, addCustom, removeCustom, duplicate, unmatched] = customCopy[language];
  return { openCustom, customLabel, addCustom, removeCustom, duplicate, unmatched,
    groups: Object.fromEntries(activityGroups.map(([id], i) => [id, groupLabels[i]])),
    keywords: Object.fromEntries(ids.map((id, i) => [id, activityLabels[i]])),
  };
}

const customCopy = {
  ko: ["원하는 활동 직접 추가", "원하는 활동 입력", "추가", "직접 추가한 활동 삭제", "이미 목록에 있는 활동이에요.", "이번 데모 코스에 반영하기 어려웠던 활동"],
  en: ["Add your own activity", "Enter an activity", "Add", "Remove custom activity", "This activity is already in the list.", "Activities we couldn’t fit into this demo itinerary"],
  ja: ["好きなアクティビティを追加", "アクティビティを入力", "追加", "追加したアクティビティを削除", "このアクティビティは登録済みです。", "デモ旅程に含められなかったアクティビティ"],
  "zh-Hans": ["添加自定义活动", "输入想做的活动", "添加", "移除自定义活动", "活动已在列表中。", "未能纳入本次演示行程的活动"],
  "zh-Hant": ["新增自訂活動", "輸入想做的活動", "新增", "移除自訂活動", "活動已在清單中。", "未能納入本次示範行程的活動"],
};
