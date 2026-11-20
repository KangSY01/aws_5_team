import { useState } from "react";
import PlaceCardDetails from "./PlaceCardDetails.jsx";
import { resolvePlaceName } from "../lib/resolvePlaceName.js";
import { formatTime } from "../lib/formatTime.js";

function PlaceCard({ option, language, reasonLanguage, copy, readOnly, canAdd, hasItinerary, busy, confirmed, stale, onConfirm }) {
  const { place, suggested, match, requestedUnavailable } = option;
  const reason = option.reason ?? copy.reasons[match];
  const { name } = resolvePlaceName(place, new Map([[place.place_id, place]]), language);
  const [start, setStart] = useState(suggested ? formatTime(suggested.start) : "");
  const [end, setEnd] = useState(suggested ? formatTime(suggested.end) : "");
  const [error, setError] = useState(null);

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
      <PlaceCardDetails place={place} name={name} language={language} copy={copy} />
      {reason && (
        <p className="chat-place-reason"><strong>{copy.reasonLabel}</strong><span lang={option.reason ? reasonLanguage : language}>{reason}</span></p>
      )}
      {!readOnly && (confirmed ? <p role="status">{copy.added}</p> : stale ? <p>{copy.stale}</p> : canAdd ? (
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
      ) : !hasItinerary && <p>{copy.noItinerary}</p>)}
    </article>
  );
}

export default function ChatPlaceCards({ message, language, copy, busy, currentPlan, onConfirm }) {
  return (
    <section className="chat-place-results" aria-label={copy.results}>
      <div className="chat-place-rail" data-multiple={message.options.length > 1}
        tabIndex={message.options.length > 1 ? 0 : undefined} role="group" aria-label={copy.results}>
        {message.options.map((option) => (
          <PlaceCard key={option.place.place_id} option={option} language={language} reasonLanguage={message.lang} copy={copy}
            readOnly={message.readOnly}
            hasItinerary={message.plan?.stops.length > 0}
            canAdd={message.plan?.stops.length > 0 && Number.isFinite(option.place.lat) && Number.isFinite(option.place.lng)} busy={busy}
            confirmed={message.confirmed === option.place.place_id}
            stale={currentPlan !== message.plan}
            onConfirm={(place, start, duration) => onConfirm(message, place, start, duration)} />
        ))}
      </div>
    </section>
  );
}
