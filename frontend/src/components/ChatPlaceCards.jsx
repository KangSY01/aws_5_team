import { useState } from "react";
import { mapLandmarks } from "../constants/mapLandmarks.js";
import { formatTime } from "../lib/formatTime.js";

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

function PlaceCard({ option, language, copy, canAdd, busy, confirmed, stale, onConfirm }) {
  const { place, suggested, requestedUnavailable } = option;
  const name = place.names[language] ?? place.names.en ?? place.place_id;
  const isPark = place.place_id === parkId;
  const landmark = mapLandmarks.find(({ id }) => id === place.place_id);
  const [address, description] = isPark ? parkDetails[language] : [null, landmark?.description[language]];
  const [start, setStart] = useState(suggested ? formatTime(suggested.start) : "");
  const [end, setEnd] = useState(suggested ? formatTime(suggested.end) : "");
  const [error, setError] = useState(null);
  const [photoFailed, setPhotoFailed] = useState(false);

  async function submit(event) {
    event.preventDefault();
    const minutes = (time) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3));
    const first = minutes(start);
    const last = minutes(end);
    if (!start || !end || last <= first) {
      setError(copy.invalidEnd);
      return;
    }
    setError(await onConfirm(place, first, last - first));
  }

  return (
    <article className="chat-place-card">
      <h3>{name}</h3>
      {isPark && !photoFailed && (
        <figure>
          <img src={photo} alt="" loading="lazy" onError={() => setPhotoFailed(true)} />
          <figcaption><a href={photoSource} target="_blank" rel="noreferrer">Vichycombo</a> · <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noreferrer">CC BY-SA 4.0</a></figcaption>
        </figure>
      )}
      {address && <p className="chat-place-address">{address}</p>}
      {description && <p>{description}</p>}
      {isPark && <a href="https://www.busan.go.kr/eng/park01" target="_blank" rel="noreferrer">{copy.details}</a>}
      {confirmed ? <p role="status">{copy.added}</p> : stale ? <p>{copy.stale}</p> : canAdd ? (
        <form className="chat-place-time" onSubmit={submit}>
          <p>{copy.prompt}</p>
          {requestedUnavailable && <small>{copy.adjusted}</small>}
          <fieldset disabled={busy}>
            <label>{copy.start}<input type="time" required value={start} onChange={(event) => { setStart(event.target.value); setError(null); }} /></label>
            <label>{copy.end}<input type="time" required value={end} onChange={(event) => { setEnd(event.target.value); setError(null); }} /></label>
          </fieldset>
          {error && <small role="alert">{error}</small>}
          <button type="submit" disabled={busy}>{copy.confirm}</button>
        </form>
      ) : <p>{copy.noItinerary}</p>}
    </article>
  );
}

export default function ChatPlaceCards({ message, language, copy, busy, currentPlan, onConfirm }) {
  return (
    <section className="chat-place-results" aria-label={copy.results}>
      <div className="chat-place-rail" data-multiple={message.options.length > 1}
        tabIndex={message.options.length > 1 ? 0 : undefined} role="group" aria-label={copy.results}>
        {message.options.map((option) => (
          <PlaceCard key={option.place.place_id} option={option} language={language} copy={copy}
            canAdd={message.plan.stops.length > 0} busy={busy}
            confirmed={message.confirmed === option.place.place_id}
            stale={currentPlan !== message.plan}
            onConfirm={(place, start, duration) => onConfirm(message, place, start, duration)} />
        ))}
      </div>
    </section>
  );
}
