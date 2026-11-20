export const languages = { ko: "한국어", en: "English", ja: "日本語", "zh-Hans": "简体中文", "zh-Hant": "繁體中文" };

const copy = {
  ko: ["나만의 부산 여행", "부산에서 무엇을 하고 싶으세요?", "해운대 근처에서 바다를 보며 반나절 보내고 싶어요.", "코스 추천받기", "부산 여행 일정", "여행 조건 수정", "일정", "지도", "개략도", "고정", "언어", "야간 테마", "코스를 찾는 중…", "아직 일정이 없습니다.", "서버에 연결할 수 없습니다.", "응답 시간이 초과됐습니다.", "일정을 불러올 수 없습니다.", "서버 응답 형식이 올바르지 않습니다.", "다시 시도"],
  en: ["Explore Busan your way", "What would you like to do in Busan?", "I’d like to spend half a day by the sea near Haeundae.", "Get a route", "Your Busan itinerary", "Edit preferences", "Itinerary", "Map", "Schematic map", "Fixed", "Language", "Night theme", "Finding your route…", "There are no stops in this itinerary.", "Couldn’t connect to the server.", "The request timed out.", "Couldn’t load the itinerary.", "Unexpected server response.", "Try again"],
  ja: ["釜山を、あなたらしく", "釜山で何をしてみたいですか？", "海雲台の近くで海を眺めながら半日過ごしたいです。", "コースを提案してもらう", "釜山の旅程", "希望を変更", "旅程", "地図", "概略図", "固定", "言語", "夜間テーマ", "コースを探しています…", "旅程に立ち寄り先がありません。", "サーバーに接続できません。", "応答がタイムアウトしました。", "旅程を取得できません。", "サーバーの応答形式が正しくありません。", "再試行"],
  "zh-Hans": ["按你的方式游釜山", "你想在釜山体验什么？", "我想在海云台附近看海，度过半天。", "获取路线推荐", "你的釜山行程", "修改偏好", "行程", "地图", "示意图", "已固定", "语言", "夜间主题", "正在推荐路线…", "本行程暂无景点。", "无法连接服务器。", "请求超时。", "无法加载行程。", "服务器响应异常。", "重试"],
  "zh-Hant": ["按你的方式遊釜山", "你想在釜山體驗什麼？", "我想在海雲臺附近看海，度過半天。", "取得路線推薦", "你的釜山行程", "修改偏好", "行程", "地圖", "示意圖", "已固定", "語言", "夜間主題", "正在推薦路線…", "本行程暫無景點。", "無法連線至伺服器。", "連線逾時。", "無法載入行程。", "伺服器回應異常。", "重試"],
};

const chatCopy = {
  ko: ["AI에게 물어보기", "전송", "채팅 닫기", "채팅 확장", "채팅 축소", "일정 있음", "BusanNow에 메시지 보내기", "샘플 일정", "홈", "채팅", "주 메뉴"],
  en: ["Ask AI", "Send", "Close chat", "Expand chat", "Reduce chat", "Route available", "Message BusanNow", "Sample itinerary", "Home", "Chat", "Main navigation"],
  ja: ["AIに聞く", "送信", "チャットを閉じる", "チャットを拡大", "チャットを縮小", "コースあり", "BusanNowへのメッセージ", "サンプル旅程", "ホーム", "チャット", "メインナビゲーション"],
  "zh-Hans": ["问 AI", "发送", "关闭聊天", "展开聊天", "缩小聊天", "已有路线", "给 BusanNow 发消息", "示例行程", "首页", "聊天", "主导航"],
  "zh-Hant": ["問 AI", "傳送", "關閉聊天", "展開聊天", "縮小聊天", "已有路線", "傳訊息給 BusanNow", "範例行程", "首頁", "聊天", "主導覽"],
};
const starterCopy = {
  ko: ["부산에서 어떤 하루를 보내고 싶으세요?", "하고 싶은 일을 알려 주세요…", "채팅 접기", ["바닷가에서 반나절", "전통시장과 길거리 음식", "비 오는 날 코스"]],
  en: ["What kind of day would you like in Busan?", "Tell me what you’d like to do…", "Collapse chat", ["Half a day by the sea", "Local markets & street food", "A rainy-day route"]],
  ja: ["釜山でどんな一日を過ごしたいですか？", "したいことを教えてください…", "チャットを折りたたむ", ["海辺で半日", "地元の市場と屋台グルメ", "雨の日のコース"]],
  "zh-Hans": ["你想在釜山度过怎样的一天？", "说说你想做什么…", "收起聊天", ["在海边度过半天", "当地市场与街头美食", "雨天游览路线"]],
  "zh-Hant": ["你想在釜山度過怎樣的一天？", "說說你想做什麼…", "收合聊天", ["在海邊度過半天", "當地市場與街頭美食", "雨天遊覽路線"]],
};
const itineraryActions = {
  ko: ["일정 접기", "일정 닫기"],
  en: ["Collapse itinerary", "Close itinerary"],
  ja: ["旅程を折りたたむ", "旅程を閉じる"],
  "zh-Hans": ["收起行程", "关闭行程"],
  "zh-Hant": ["收合行程", "關閉行程"],
};

const profileCopy = {
  ko: ["프로필", "게스트로 이용 중", "계정 관리", "현재 로그인과 계정 관리 기능을 제공하지 않습니다."],
  en: ["Profile", "Browsing as a guest", "Account management", "Sign-in and account management are currently unavailable."],
  ja: ["プロフィール", "ゲストとして利用中", "アカウント管理", "現在、ログインとアカウント管理は利用できません。"],
  "zh-Hans": ["个人资料", "正在以访客身份浏览", "账号管理", "目前无法登录或管理账号。"],
  "zh-Hant": ["個人資料", "正在以訪客身分瀏覽", "帳號管理", "目前無法登入或管理帳號。"],
};

const tripCopy = {
  ko: ["여행 시작", "여행 종료", "여행 중", "다음 장소", "AI에게 코스 추천받기"],
  en: ["Start trip", "End trip", "Trip in progress", "Next stop", "Ask AI for an itinerary"],
  ja: ["旅行を始める", "旅行を終了", "旅行中", "次の行き先", "AIにコースを提案してもらう"],
  "zh-Hans": ["开始旅行", "结束旅行", "旅行中", "下一站", "让 AI 推荐行程"],
  "zh-Hant": ["開始旅行", "結束旅行", "旅行中", "下一站", "請 AI 推薦行程"],
};

const emergencyCopy = {
  ko: {
    trigger: "긴급 도움", title: "긴급 신고",
    warning: "실제 긴급 상황에서만 이용해 주세요. 장난 전화는 실제로 도움이 필요한 사람의 신고를 지연시킬 수 있어요.",
    notice: "신고처를 누르면 휴대전화의 전화 앱이 열립니다.",
    police: "경찰 112에 전화", rescue: "소방·구급 119에 전화", cancel: "취소",
  },
  en: {
    trigger: "Emergency help", title: "Emergency calls",
    warning: "Use this only in a real emergency. Prank calls can delay help for people who need it.",
    notice: "Selecting a service opens your phone app.",
    police: "Call police (112)", rescue: "Call fire or ambulance (119)", cancel: "Cancel",
  },
  ja: {
    trigger: "緊急時の連絡", title: "緊急通報",
    warning: "実際の緊急時にのみご利用ください。いたずら電話は、本当に助けが必要な方への対応を遅らせるおそれがあります。",
    notice: "通報先を選ぶと、電話アプリが開きます。",
    police: "警察（112）に電話", rescue: "消防・救急（119）に電話", cancel: "キャンセル",
  },
  "zh-Hans": {
    trigger: "紧急求助", title: "紧急呼叫",
    warning: "仅在真正的紧急情况下使用。恶作剧电话可能会延误真正需要帮助的人获得救援。",
    notice: "选择紧急服务后，手机将打开电话应用。",
    police: "拨打报警电话 112", rescue: "拨打消防和急救电话 119", cancel: "取消",
  },
  "zh-Hant": {
    trigger: "緊急求助", title: "緊急通報",
    warning: "僅在真正的緊急情況下使用。惡作劇電話可能會延誤真正需要幫助的人獲得救援。",
    notice: "選擇緊急服務後，手機會開啟電話應用程式。",
    police: "撥打報警電話 112", rescue: "撥打消防及救護電話 119", cancel: "取消",
  },
};

const locationLabels = {
  ko: ["내 위치 찾기", "위치 확인 중…", "위치 권한이 거부됐어요.", "현재 위치를 가져올 수 없어요."],
  en: ["Find my location", "Finding your location…", "Location permission was denied.", "Could not find your location."],
  ja: ["現在地を表示", "現在地を確認中…", "位置情報の使用が許可されていません。", "現在地を取得できませんでした。"],
  "zh-Hans": ["查找我的位置", "正在获取位置…", "位置权限已被拒绝。", "无法获取当前位置。"],
  "zh-Hant": ["尋找我的位置", "正在取得位置…", "位置權限已遭拒絕。", "無法取得目前位置。"],
};

export function getTravelCopy(language) {
  const [intro, prompt, example, submit, title, edit, itinerary, map, schematic, locked, languageLabel, night, loading, empty, network, timeout, http, invalidResponse, retry] = copy[language];
  const [ask, send, close, expand, reduce, ready, messageLabel, sampleTitle, home, chat, navigation] = chatCopy[language];
  const [greeting, placeholder, collapse, suggestions] = starterCopy[language];
  const [collapseItinerary, closeItinerary] = itineraryActions[language];
  const [profile, guest, account, accountUnavailable] = profileCopy[language];
  const [startTrip, endTrip, traveling, nextPlace, askForRoute] = tripCopy[language];
  const [find, pending, denied, unavailable] = locationLabels[language];
  return {
    location: { find, pending, denied, unavailable },
    emergency: emergencyCopy[language],
    startTrip, endTrip, traveling, nextPlace, askForRoute,
    profile, guest, account, accountUnavailable,
    collapseItinerary, closeItinerary,
    greeting, placeholder, collapse, suggestions,
    ask, send, close, expand, reduce, ready, messageLabel, sampleTitle, home, chat, navigation,
    intro, prompt, example, submit, title, edit, itinerary, map, schematic, locked,
    languageLabel, night, loading, empty, retry,
    errorTitles: { network, timeout, http, invalid_response: invalidResponse },
  };
}
