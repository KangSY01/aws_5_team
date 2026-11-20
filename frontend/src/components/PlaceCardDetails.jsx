import { useState } from "react";
import { mapLandmarks } from "../constants/mapLandmarks.js";

const parkId = "busan-citizens-park";
const photoSource = "https://commons.wikimedia.org/wiki/File:Busan_Citizens_Park_%22mirror_pond%22.jpg";
const photo = "https://thumb.wikimedia.org/wikipedia/commons/thumb/7/73/Busan_Citizens_Park_%22mirror_pond%22.jpg/500px-Busan_Citizens_Park_%22mirror_pond%22.jpg";
const parkDetails = {
  ko: ["부산광역시 부산진구 시민공원로 73", "잔디광장과 산책로가 있는 부산진구의 도심 공원입니다."],
  en: ["73 Simingongwon-ro, Busanjin-gu, Busan", "An urban park in Busanjin-gu with a lawn plaza and walking trails."],
  ja: ["釜山広域市 釜山鎮区 市民公園路73", "芝生広場と散歩道がある釜山鎮区の都市公園です。"],
  "zh-Hans": ["釜山广域市釜山镇区市民公园路73号", "釜山镇区的城市公园，设有草坪广场和步道。"],
  "zh-Hant": ["釜山廣域市釜山鎮區市民公園路73號", "釜山鎮區的城市公園，設有草坪廣場和步道。"],
};

export default function PlaceCardDetails({ place, name, language, copy }) {
  const isPark = place.place_id === parkId;
  const landmark = mapLandmarks.find(({ id }) => id === place.place_id);
  const [knownAddress, description] = isPark ? parkDetails[language] : [null, landmark?.description[language]];
  const address = place.address || knownAddress;
  const detailUrl = place.url || (isPark ? "https://www.busan.go.kr/eng/park01"
    : "https://map.kakao.com/link/search/" + encodeURIComponent("부산 " + name));
  const [photoFailed, setPhotoFailed] = useState(false);
  return (
    <>
      {place.categoryLabel && <small>{place.categoryLabel}</small>}
      {isPark && !photoFailed && (
        <figure>
          <img src={photo} alt="" loading="lazy" onError={() => setPhotoFailed(true)} />
          <figcaption><a href={photoSource} target="_blank" rel="noreferrer">Vichycombo</a> · <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noreferrer">CC BY-SA 4.0</a></figcaption>
        </figure>
      )}
      {address && <p className="chat-place-address">{address}</p>}
      {description && <p>{description}</p>}
      {place.nearest_station && <small>{copy.nearestStation} · {place.nearest_station}</small>}
      {place.phone && <a href={"tel:" + place.phone}>{place.phone}</a>}
      <a href={detailUrl} target="_blank" rel="noreferrer">{copy.details}</a>
    </>
  );
}
