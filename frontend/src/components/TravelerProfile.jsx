import { useRef, useState } from "react";
import "./traveler-profile.css";

export const travelerProfileKey = "busannow.traveler-profile";

const translations = {
  ko: ["여행자 프로필", "이름 또는 닉네임", "나이", "성별", "국적", "여행 시 참고할 사항", "예: 오래 걷기 어려워요", "저장하고 시작", "나중에", "프로필 편집", "저장", "취소", "응답하지 않음", "여성", "남성", "원하는 항목만 입력해 주세요."],
  en: ["Traveler profile", "Name or nickname", "Age", "Gender", "Nationality", "Travel notes", "e.g. I need shorter walks.", "Save and start", "Later", "Edit profile", "Save", "Cancel", "Prefer not to answer", "Woman", "Man", "Fill in any fields you like."],
  ja: ["旅行者プロフィール", "名前またはニックネーム", "年齢", "性別", "国籍", "旅行時の配慮事項", "例：長い距離を歩くのが難しいです。", "保存して始める", "あとで", "プロフィールを編集", "保存", "キャンセル", "回答しない", "女性", "男性", "入力したい項目だけご記入ください。"],
  "zh-Hans": ["旅行者资料", "姓名或昵称", "年龄", "性别", "国籍", "旅行注意事项", "例如：我不方便长时间步行。", "保存并开始", "稍后", "编辑资料", "保存", "取消", "不愿回答", "女性", "男性", "请填写您想填写的项目。"],
  "zh-Hant": ["旅行者資料", "姓名或暱稱", "年齡", "性別", "國籍", "旅行注意事項", "例如：我不方便長時間步行。", "儲存並開始", "稍後", "編輯資料", "儲存", "取消", "不願回答", "女性", "男性", "請填寫您想填寫的項目。"],
};

const genders = ["", "woman", "man"];

// 식사 제한 (D). 값은 백엔드 Profile.diet 로 그대로 보낸다 (영어 토큰, 모델이 읽는다).
// 종교는 묻지 않는다: 추천에 필요한 것은 먹지 않는 음식이다. 힌두교 신자는 no beef 를 고르면 된다.
export const dietOptions = ["halal", "no pork", "no beef", "vegetarian", "vegan"];
const dietCopy = {
  ko: ["식사 제한", "해당하는 것을 모두 골라 주세요.", ["할랄", "돼지고기 제외", "소고기 제외", "채식", "비건"]],
  en: ["Dietary needs", "Choose all that apply.", ["Halal", "No pork", "No beef", "Vegetarian", "Vegan"]],
  ja: ["食事の制限", "当てはまるものをすべて選んでください。", ["ハラール", "豚肉なし", "牛肉なし", "ベジタリアン", "ヴィーガン"]],
  "zh-Hans": ["饮食限制", "请选择所有适用项。", ["清真", "不吃猪肉", "不吃牛肉", "素食", "纯素"]],
  "zh-Hant": ["飲食限制", "請選擇所有適用項目。", ["清真", "不吃豬肉", "不吃牛肉", "素食", "純素"]],
};
export function dietLabels(language) {
  const [, , names] = dietCopy[language] ?? dietCopy.en;
  return Object.fromEntries(dietOptions.map((value, index) => [value, names[index]]));
}
const photoCopy = {
  ko: ["사진 추가", "사진 변경", "삭제", "사진을 열 수 없어요. 다른 사진을 골라 주세요."],
  en: ["Add photo", "Change photo", "Remove", "Couldn’t open this photo. Choose another one."],
  ja: ["写真を追加", "写真を変更", "削除", "写真を開けませんでした。別の写真を選んでください。"],
  "zh-Hans": ["添加照片", "更换照片", "移除", "无法打开照片，请选择另一张。"],
  "zh-Hant": ["加入照片", "更換照片", "移除", "無法開啟照片，請選擇另一張。"],
};

async function makeProfilePhoto(file) {
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    const side = Math.min(image.naturalWidth, image.naturalHeight);
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = Math.min(side, 256);
    canvas.getContext("2d").drawImage(image, (image.naturalWidth - side) / 2,
      (image.naturalHeight - side) / 2, side, side, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/webp", 0.85);
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function travelerCopy(language) {
  const [title, name, age, gender, country, notes, example, start, later, edit, save, cancel, ...rest] = translations[language];
  return { title, name, age, gender, country, notes, example, start, later, edit, save, cancel,
    genderNames: Object.fromEntries(genders.map((value, index) => [value, rest[index]])), optional: rest[3] };
}

export default function TravelerProfileForm({ language, initial, firstVisit = false, onSave, onCancel }) {
  const copy = travelerCopy(language);
  const [addPhoto, changePhoto, removePhoto, invalidPhoto] = photoCopy[language];
  const photoInput = useRef(null);
  const [loadingPhoto, setLoadingPhoto] = useState(false);
  const [photoError, setPhotoError] = useState(false);
  const [draft, setDraft] = useState({ name: "", age: "", gender: "", country: "", notes: "", ...initial,
    gender: genders.includes(initial?.gender) ? initial.gender : "",
    diet: Array.isArray(initial?.diet) ? initial.diet.filter((value) => dietOptions.includes(value)) : [] });
  const [dietTitle, dietHint, dietNames] = dietCopy[language] ?? dietCopy.en;
  function toggleDiet(value) {
    setDraft((current) => ({ ...current, diet: current.diet.includes(value)
      ? current.diet.filter((item) => item !== value) : [...current.diet, value] }));
  }

  async function selectPhoto(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setLoadingPhoto(true);
    setPhotoError(false);
    try {
      const photo = await makeProfilePhoto(file);
      setDraft((current) => ({ ...current, photo }));
    } catch {
      setPhotoError(true);
    } finally {
      setLoadingPhoto(false);
    }
  }
  function field(key) {
    return { name: key, value: draft[key], onChange: (event) => {
      const value = event.target.value;
      setDraft((current) => ({ ...current, [key]: value }));
    } };
  }

  return <form className="traveler-profile-form" onSubmit={(event) => {
    event.preventDefault();
    if (loadingPhoto) return;
    onSave(Object.fromEntries(Object.entries(draft).map(([key, value]) => [key, typeof value === "string" ? value.trim() : value])));
  }}>
    <p className="traveler-profile-optional">{copy.optional}</p>
    <div className="traveler-profile-photo">
      {draft.photo && <img className="traveler-avatar" src={draft.photo} alt="" width="68" height="68" />}
      <input ref={photoInput} type="file" accept="image/*" aria-label={addPhoto} hidden onChange={selectPhoto} />
      <button type="button" disabled={loadingPhoto} onClick={() => photoInput.current.click()}>
        {draft.photo ? changePhoto : addPhoto}
      </button>
      {draft.photo && <button type="button" disabled={loadingPhoto} onClick={() => {
        setPhotoError(false);
        setDraft((current) => ({ ...current, photo: "" }));
      }}>{removePhoto}</button>}
    </div>
    {photoError && <p className="traveler-profile-optional" role="alert">{invalidPhoto}</p>}
    <label>{copy.name}<input {...field("name")} autoComplete="nickname" maxLength={80} /></label>
    <div className="traveler-profile-row">
      <label>{copy.age}<input {...field("age")} type="number" inputMode="numeric" min={0} step={1} /></label>
      <label>{copy.gender}<select {...field("gender")}>
        {genders.map((value) => <option key={value} value={value}>{copy.genderNames[value]}</option>)}
      </select></label>
    </div>
    <label>{copy.country}<input {...field("country")} autoComplete="off" maxLength={80} /></label>
    <fieldset className="traveler-diet">
      <legend>{dietTitle}</legend>
      <p className="traveler-profile-optional">{dietHint}</p>
      <div className="traveler-diet-options">
        {dietOptions.map((value, index) => (
          <label key={value} className="traveler-diet-chip">
            <input type="checkbox" checked={draft.diet.includes(value)} onChange={() => toggleDiet(value)} />
            <span>{dietNames[index]}</span>
          </label>
        ))}
      </div>
    </fieldset>
    <label>{copy.notes}<textarea {...field("notes")} rows={2} maxLength={1000} placeholder={copy.example} /></label>
    <footer>
      <button type="button" onClick={onCancel}>{firstVisit ? copy.later : copy.cancel}</button>
      <button type="submit" disabled={loadingPhoto}>{firstVisit ? copy.start : copy.save}</button>
    </footer>
  </form>;
}
