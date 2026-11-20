const fields = ["title", "photo", "voice", "source", "target", "camera", "upload", "photoSubmit", "input", "mic", "stop", "listening", "submit", "working", "original", "result", "same", "noText", "micUnsupported", "micDenied", "micError", "unavailable", "failed", "imageError", "preview", "photoNeeded"];

const translations = {
  ko: ["번역", "이미지 번역", "음성 번역", "원문 언어", "번역 언어", "카메라로 촬영", "사진 업로드", "이미지 번역하기", "번역할 내용을 입력하세요", "음성 입력", "중지", "듣는 중…", "번역하기", "처리 중…", "원문", "번역 결과", "원문과 다른 번역 언어를 골라 주세요.", "글자를 찾지 못했어요. 다시 찍거나 다른 사진을 골라 주세요.", "이 브라우저는 음성 인식을 지원하지 않아요. 직접 입력해 주세요.", "마이크에 접근할 수 없어요. 권한을 확인하거나 직접 입력해 주세요.", "음성을 인식하지 못했어요. 다시 시도하거나 직접 입력해 주세요.", "이 환경에서는 번역 서비스를 사용할 수 없어요.", "처리에 실패했어요. 다시 시도해 주세요.", "사진을 열 수 없어요. 다른 사진을 골라 주세요.", "선택한 사진 미리보기", "번역할 사진을 촬영하거나 업로드해 주세요."],
  en: ["Translate", "Image translation", "Voice translation", "Source language", "Target language", "Take a photo", "Upload photo", "Translate image", "Enter text to translate", "Voice input", "Stop", "Listening…", "Translate", "Processing…", "Original", "Translation", "Choose a different target language.", "No text found. Retake the photo or choose another one.", "Speech recognition is unavailable. You can still type.", "Microphone access is unavailable. Check permissions or type instead.", "Speech was not recognized. Try again or type instead.", "Translation is unavailable in this environment.", "Something went wrong. Try again.", "Could not open the photo. Choose another one.", "Selected photo preview", "Take or upload a photo to translate."],
  ja: ["翻訳", "画像翻訳", "音声翻訳", "原文の言語", "翻訳先の言語", "写真を撮る", "写真を選ぶ", "画像を翻訳", "翻訳する文章を入力", "音声入力", "停止", "聞き取り中…", "翻訳する", "処理中…", "原文", "翻訳結果", "原文と異なる言語を選んでください。", "文字が見つかりません。撮り直すか別の写真を選んでください。", "音声認識は利用できません。文字を入力してください。", "マイクを使用できません。権限を確認するか文字を入力してください。", "音声を認識できませんでした。再試行するか文字を入力してください。", "この環境では翻訳を利用できません。", "処理に失敗しました。もう一度お試しください。", "写真を開けません。別の写真を選んでください。", "選択した写真のプレビュー", "翻訳する写真を撮影するか選んでください。"],
  "zh-Hans": ["翻译", "图片翻译", "语音翻译", "原文语言", "目标语言", "拍照", "上传照片", "翻译图片", "输入要翻译的内容", "语音输入", "停止", "正在聆听…", "翻译", "处理中…", "原文", "翻译结果", "请选择与原文不同的目标语言。", "未找到文字。请重拍或选择其他照片。", "此浏览器不支持语音识别，请手动输入。", "无法访问麦克风，请检查权限或手动输入。", "未能识别语音，请重试或手动输入。", "当前环境无法使用翻译服务。", "处理失败，请重试。", "无法打开照片，请选择其他照片。", "所选照片预览", "请拍摄或上传要翻译的照片。"],
  "zh-Hant": ["翻譯", "圖片翻譯", "語音翻譯", "原文語言", "目標語言", "拍照", "上傳照片", "翻譯圖片", "輸入要翻譯的內容", "語音輸入", "停止", "正在聆聽…", "翻譯", "處理中…", "原文", "翻譯結果", "請選擇與原文不同的目標語言。", "找不到文字。請重拍或選擇其他照片。", "此瀏覽器不支援語音辨識，請手動輸入。", "無法使用麥克風，請檢查權限或手動輸入。", "無法辨識語音，請重試或手動輸入。", "目前環境無法使用翻譯服務。", "處理失敗，請重試。", "無法開啟照片，請選擇其他照片。", "所選照片預覽", "請拍攝或上傳要翻譯的照片。"],
};

const voicePanelCopy = {
  ko: ["번역 닫기", "말할 언어", "원문 언어를 감지하지 못했어요. 입력한 언어를 골라 주세요."],
  en: ["Close translation", "Speaking language", "We couldn't detect the source language. Choose the language you entered."],
  ja: ["翻訳を閉じる", "話す言語", "原文の言語を検出できませんでした。入力した言語を選択してください。"],
  "zh-Hans": ["关闭翻译", "口述语言", "未能检测到原文语言。请选择输入的语言。"],
  "zh-Hant": ["關閉翻譯", "口述語言", "未能偵測到原文語言。請選擇輸入的語言。"],
};

const photoLanguageCopy = {
  ko: ["번역할 언어", "감지된 언어", "원문 언어 수정", "원문 언어 선택", "원문 언어를 감지하지 못했어요. 사진 속 언어를 골라 주세요."],
  en: ["Translate into", "Detected language", "Correct source language", "Choose source language", "We couldn't detect the source language. Choose the language in the photo."],
  ja: ["翻訳先の言語", "検出された言語", "原文の言語を修正", "原文の言語を選択", "原文の言語を検出できませんでした。写真の言語を選択してください。"],
  "zh-Hans": ["翻译成", "检测到的语言", "修改原文语言", "选择原文语言", "未能检测到原文语言。请选择照片中的语言。"],
  "zh-Hant": ["翻譯成", "偵測到的語言", "修改原文語言", "選擇原文語言", "未能偵測到原文語言。請選擇照片中的語言。"],
};

const textPanelCopy = {
  ko: ["텍스트 번역", "자동 감지", "번역 결과가 여기에 표시돼요."],
  en: ["Text translation", "Auto-detect", "Your translation appears here."],
  ja: ["テキスト翻訳", "自動検出", "翻訳結果がここに表示されます。"],
  "zh-Hans": ["文本翻译", "自动检测", "译文将显示在这里。"],
  "zh-Hant": ["文字翻譯", "自動偵測", "譯文將顯示在這裡。"],
};

const photoResultCopy = {
  ko: ["매워요", "맵지 않아요", "맵기 여부를 확인할 수 없어요.", "JPEG 또는 PNG 사진을 선택해 주세요.", "사진을 업로드하지 못했어요. 다시 시도해 주세요.", "업로드한 사진을 찾을 수 없어요. 다시 시도해 주세요.", "사진 번역 서버에서 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", "사진 번역 응답이 지연되고 있어요. 다시 시도해 주세요."],
  en: ["Spicy", "Not spicy", "Spiciness could not be confirmed.", "Choose a JPEG or PNG photo.", "Could not upload the photo. Try again.", "The uploaded photo could not be found. Try again.", "The photo translation server encountered an error. Try again shortly.", "Photo translation timed out. Try again."],
  ja: ["辛い", "辛くない", "辛さは確認できません。", "JPEGまたはPNGの写真を選んでください。", "写真をアップロードできませんでした。もう一度お試しください。", "アップロードした写真が見つかりません。もう一度お試しください。", "写真翻訳サーバーでエラーが発生しました。しばらくしてからお試しください。", "写真翻訳がタイムアウトしました。もう一度お試しください。"],
  "zh-Hans": ["辣", "不辣", "无法确认是否辛辣。", "请选择 JPEG 或 PNG 照片。", "照片上传失败，请重试。", "找不到已上传的照片，请重试。", "图片翻译服务器出错，请稍后重试。", "图片翻译超时，请重试。"],
  "zh-Hant": ["辣", "不辣", "無法確認是否辛辣。", "請選擇 JPEG 或 PNG 照片。", "照片上傳失敗，請重試。", "找不到已上傳的照片，請重試。", "圖片翻譯伺服器發生錯誤，請稍後重試。", "圖片翻譯逾時，請重試。"],
};

export function getTranslationCopy(language) {
  const [close, speakingLanguage, detectVoiceFailed] = voicePanelCopy[language];
  const labels = Object.fromEntries(fields.map((field, index) => [field, translations[language][index]]));
  const [photoTarget, detected, correctSource, chooseSource, detectFailed] = photoLanguageCopy[language];
  const [text, autoDetect, resultPlaceholder] = textPanelCopy[language];
  const [spicyYes, spicyNo, spicyUnknown, photoInvalid, photoUploadFailed, photoMissing, photoServerError, photoTimeout] = photoResultCopy[language];
  return { ...labels, text, autoDetect, resultPlaceholder, close, speakingLanguage, detectVoiceFailed, photoTarget, detected, correctSource, chooseSource, detectFailed,
    spicyYes, spicyNo, spicyUnknown, photoInvalid, photoUploadFailed, photoMissing, photoServerError, photoTimeout };
}
