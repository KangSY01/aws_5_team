export const languages = { en: "English", ja: "日本語", "zh-Hans": "简体中文", "zh-Hant": "繁體中文" };

const copy = {
  en: ["Explore Busan your way", "What would you like to do in Busan?", "I’d like to spend half a day by the sea near Haeundae.", "Get a route", "Your Busan itinerary", "Edit preferences", "Itinerary", "Map", "Schematic map", "Fixed", "Language", "Night theme", "Finding your route…", "There are no stops in this itinerary.", "Couldn’t connect to the server.", "The request timed out.", "Couldn’t load the itinerary.", "Unexpected server response.", "Try again"],
  ja: ["釜山を、あなたらしく", "釜山で何をしてみたいですか？", "海雲台の近くで海を眺めながら半日過ごしたいです。", "コースを提案してもらう", "釜山の旅程", "希望を変更", "旅程", "地図", "概略図", "固定", "言語", "夜間テーマ", "コースを探しています…", "旅程に立ち寄り先がありません。", "サーバーに接続できません。", "応答がタイムアウトしました。", "旅程を取得できません。", "サーバーの応答形式が正しくありません。", "再試行"],
  "zh-Hans": ["按你的方式游釜山", "你想在釜山体验什么？", "我想在海云台附近看海，度过半天。", "获取路线推荐", "你的釜山行程", "修改偏好", "行程", "地图", "示意图", "已固定", "语言", "夜间主题", "正在推荐路线…", "本行程暂无景点。", "无法连接服务器。", "请求超时。", "无法加载行程。", "服务器响应异常。", "重试"],
  "zh-Hant": ["按你的方式遊釜山", "你想在釜山體驗什麼？", "我想在海雲臺附近看海，度過半天。", "取得路線推薦", "你的釜山行程", "修改偏好", "行程", "地圖", "示意圖", "已固定", "語言", "夜間主題", "正在推薦路線…", "本行程暫無景點。", "無法連線至伺服器。", "連線逾時。", "無法載入行程。", "伺服器回應異常。", "重試"],
};

const chatCopy = {
  en: ["Ask AI", "Send", "Close chat", "Expand chat", "Reduce chat", "Route available", "Message BusanNow", "Sample itinerary", "Home", "Chat", "Main navigation"],
  ja: ["AIに聞く", "送信", "チャットを閉じる", "チャットを拡大", "チャットを縮小", "コースあり", "BusanNowへのメッセージ", "サンプル旅程", "ホーム", "チャット", "メインナビゲーション"],
  "zh-Hans": ["问 AI", "发送", "关闭聊天", "展开聊天", "缩小聊天", "已有路线", "给 BusanNow 发消息", "示例行程", "首页", "聊天", "主导航"],
  "zh-Hant": ["問 AI", "傳送", "關閉聊天", "展開聊天", "縮小聊天", "已有路線", "傳訊息給 BusanNow", "範例行程", "首頁", "聊天", "主導覽"],
};
const starterCopy = {
  en: ["What kind of day would you like in Busan?", "Tell me what you’d like to do…", "Collapse chat", ["Half a day by the sea", "Local markets & street food", "A rainy-day route"]],
  ja: ["釜山でどんな一日を過ごしたいですか？", "したいことを教えてください…", "チャットを折りたたむ", ["海辺で半日", "地元の市場と屋台グルメ", "雨の日のコース"]],
  "zh-Hans": ["你想在釜山度过怎样的一天？", "说说你想做什么…", "收起聊天", ["在海边度过半天", "当地市场与街头美食", "雨天游览路线"]],
  "zh-Hant": ["你想在釜山度過怎樣的一天？", "說說你想做什麼…", "收合聊天", ["在海邊度過半天", "當地市場與街頭美食", "雨天遊覽路線"]],
};
export function getTravelCopy(language) {
  const [intro, prompt, example, submit, title, edit, itinerary, map, schematic, locked, languageLabel, night, loading, empty, network, timeout, http, invalidResponse, retry] = copy[language];
  const [ask, send, close, expand, reduce, ready, messageLabel, sampleTitle, home, chat, navigation] = chatCopy[language];
  const [greeting, placeholder, collapse, suggestions] = starterCopy[language];
  return {
    greeting, placeholder, collapse, suggestions,
    ask, send, close, expand, reduce, ready, messageLabel, sampleTitle, home, chat, navigation,
    intro, prompt, example, submit, title, edit, itinerary, map, schematic, locked,
    languageLabel, night, loading, empty, retry,
    errorTitles: { network, timeout, http, invalid_response: invalidResponse },
  };
}
