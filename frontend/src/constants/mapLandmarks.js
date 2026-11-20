import places from "../mocks/places.json";
import regionalPlaces from "../mocks/regionalPlaces.json";

const locales = ["ko", "en", "ja", "zh-Hans", "zh-Hant"];
export const closeLandmark = {
  ko: "장소 소개 닫기",
  en: "Close landmark details",
  ja: "名所の紹介を閉じる",
  "zh-Hans": "关闭地标介绍",
  "zh-Hant": "關閉地標介紹",
};
const bridge = {
  place_id: "gwangan-bridge",
  lat: 35.14569,
  lng: 129.128385,
  names: { ko: "광안대교", en: "Gwangan Bridge", ja: "広安大橋", "zh-Hans": "广安大桥", "zh-Hant": "廣安大橋" },
};
const placesById = new Map([bridge, ...places, ...regionalPlaces].map((place) => [place.place_id, place]));

export const mapLandmarks = [
  ["gwangan-bridge", 10, 64, [
    "광안리 앞바다를 가로지르는 현수교입니다. 밤에는 조명이 수영만을 밝힙니다.",
    "This suspension bridge spans the water off Gwangalli. At night it lights up Suyeong Bay.",
    "広安里沖に架かる吊り橋です。夜にはライトアップが水営湾を彩ります。",
    "这座悬索桥横跨广安里近海。夜间灯光点亮水营湾。",
    "這座懸索橋橫跨廣安里近海。夜間燈光點亮水營灣。",
  ]],
  ["geumjeong-east-gate", 10, 58, [
    "금정산 능선을 따라 이어지는 산성의 동문입니다. 동문에서 성벽을 따라 산길을 걸을 수 있습니다.",
    "This gate sits on the fortress walls that follow the Geumjeongsan ridge. A trail runs along the stone walls.",
    "金井山の尾根に沿って延びる山城の東門です。石垣沿いに山道が続きます。",
    "这是沿金井山山脊延伸的山城东门。步道沿石墙而行。",
    "這是沿金井山山脊延伸的山城東門。步道沿石牆而行。",
  ]],
  ["dadaepo-beach", 10, 56, [
    "낙동강 하구와 바다가 만나는 넓은 모래사장입니다. 해 질 무렵에는 갯벌 위로 노을이 펼쳐집니다.",
    "A broad sandy beach where the Nakdong River meets the sea. At sunset, the tidal flats catch the evening light.",
    "洛東江の河口と海が出会う広い砂浜です。夕暮れには干潟に夕日が映ります。",
    "这里是洛东江入海处的宽阔沙滩。傍晚可看夕阳映照滩涂。",
    "這裡是洛東江入海處的寬闊沙灘。傍晚可看夕陽映照灘塗。",
  ]],
  ["taejongdae", 10, 56, [
    "영도 남쪽 끝의 해안 절벽입니다. 숲길을 따라 걸으면 바다와 영도등대가 보입니다.",
    "Sea cliffs mark the southern tip of Yeongdo. The wooded trails look out over the sea and Yeongdo Lighthouse.",
    "影島の南端にある海食崖です。森の小道から海と影島灯台を望めます。",
    "这里是影岛南端的海岸峭壁。沿林间步道可远眺大海与影岛灯塔。",
    "這裡是影島南端的海岸峭壁。沿林間步道可遠眺大海與影島燈塔。",
  ]],
  ["gamcheon-village", 10, 56, [
    "산비탈을 따라 집들이 계단처럼 들어선 마을입니다. 골목 곳곳에서 벽화와 작품을 만날 수 있습니다.",
    "Houses climb the hillside in colorful tiers. Murals and artworks dot the narrow lanes.",
    "家々が山の斜面に階段状に並ぶ集落です。細い路地に壁画や作品が点在しています。",
    "彩色民居沿山坡层层排列。曲折小巷中点缀着壁画和艺术作品。",
    "彩色民居沿山坡層層排列。曲折巷弄中點綴著壁畫和藝術作品。",
  ]],
  ["haeundae-beach", 12, 58, [
    "도심과 맞닿은 넓은 백사장입니다. 해변을 따라 동백섬 방향으로 걸을 수 있습니다.",
    "A broad city beach backed by the Haeundae skyline. The waterfront path leads toward Dongbaekseom Island.",
    "街に面した広い白砂のビーチです。海沿いを歩いて冬柏島へ向かえます。",
    "这片宽阔的沙滩紧邻城区。沿海滨步道可走向冬柏岛。",
    "這片寬闊的沙灘緊鄰市區。沿海濱步道可走向冬柏島。",
  ]],
  ["busan-tower", 12, 44, [
    "용두산공원에 우뚝 선 전망탑입니다. 전망대에서 원도심과 부산항을 내려다볼 수 있습니다.",
    "The observation tower rises above Yongdusan Park. Its deck overlooks the old downtown and Busan Harbor.",
    "龍頭山公園に立つ展望塔です。展望台から旧市街と釜山港を見渡せます。",
    "观景塔矗立在龙头山公园内。从观景台可俯瞰旧城区与釜山港。",
    "觀景塔矗立在龍頭山公園內。從觀景台可俯瞰舊市區與釜山港。",
  ]],
].map(([id, minZoom, width, introductions]) => ({
  id, minZoom, width, ...placesById.get(id),
  description: Object.fromEntries(locales.map((locale, index) => [locale, introductions[index]])),
}));
