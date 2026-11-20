import PlaceCardDetails from "./PlaceCardDetails.jsx";
import { Fragment, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { fetchMapEvents, mapEventName } from "../api/eventsClient.js";
import { resolvePlaceName } from "../lib/resolvePlaceName.js";
import { stopDate } from "../lib/itineraryTiming.js";
import { formatTime } from "../lib/formatTime.js";

function timeRange(stop) {
  return formatTime(stop.start) + "–" + formatTime(stop.end);
}

function DelayChange({ before, after, sharedPlace, placeName }) {
  if (before && !after) {
    return sharedPlace ? null : <p className="guardian-delay-change">{placeName(before)}</p>;
  }
  if (before && after && before.place_id === after.place_id) {
    return (
      <div className="guardian-delay-change">
        {!sharedPlace && <strong>{placeName(before)}</strong>}
        <p className="guardian-time-comparison">
          <span className="guardian-time-before">{timeRange(before)}</span>
          <span className="guardian-time-after">→ <strong>{timeRange(after)}</strong></span>
        </p>
      </div>
    );
  }
  return <StandardChange before={before} after={after} placeName={placeName} />;
}

function StandardChange({ before, after, placeName, range = timeRange }) {
  return (
    <p>{before && (
      <span className={after ? undefined : "guardian-removal"}>{placeName(before)} · {range(before)}</span>
    )}{before && after && " → "}{after && (
      <strong>{placeName(after)} · {range(after)}</strong>
    )}</p>
  );
}

function Reason({ issue, target, language, copy, events }) {
  const detail = issue?.detail;
  const eventName = issue?.type === "crowded" ? detail?.match(/행사일 가중\((.*)\)\s*$/u)?.[1] : null;
  const findEvent = (entries) => entries?.find((event) => event.name === eventName || event.names?.ko === eventName);
  const existing = eventName && findEvent(events);
  const date = target && stopDate(target.start);
  const [matched, setMatched] = useState(null);

  useEffect(() => {
    if (!eventName || !date || existing) return;
    const controller = new AbortController();
    fetchMapEvents(date, controller.signal).then((entries) => {
      if (!controller.signal.aborted) setMatched(entries.find((event) => event.name === eventName || event.names?.ko === eventName));
    }).catch(() => {});
    return () => controller.abort();
  }, [date, eventName, existing]);

  if (!detail) return null;
  if (issue.type !== "crowded") {
    const recognized = /강수확률|휴무일|운영시간|^이동 \d+분/u.test(detail);
    return <p className="guardian-reason">{recognized ? copy.reasons[issue.type] ?? detail : detail}</p>;
  }
  if (!/집중률|혼잡 데이터 없음|행사일 가중/u.test(detail)) return <p className="guardian-reason">{detail}</p>;

  const weekday = target && new Intl.DateTimeFormat(language, { weekday: "long", timeZone: "Asia/Seoul" }).format(new Date(target.start));
  const crowd = /요일 규칙/u.test(detail) ? copy.reasons.crowdWeekday
    : weekday && !detail.startsWith("혼잡 데이터 없음") ? copy.reasons.crowdDay.replace("{day}", () => weekday)
    : copy.crowdingWarning;
  const localizedEvent = existing || matched;
  return <p className="guardian-reason">{crowd}{eventName && <> {copy.reasons.nearbyEvent.replace("{event}", () =>
    localizedEvent ? mapEventName(localizedEvent, language) : eventName)}</>}</p>;
}

export default function GuardianAlternatives({ alternative, copy, placeCopy, placesById, language, events, busy, error, onApply, onClose }) {
  const dialog = useRef(null);
  const titleId = useId();
  const [openCandidate, setOpenCandidate] = useState(null);
  const isDelay = alternative.kind === "delay";
  const affected = new Set();
  if (isDelay) {
    for (const { changes } of alternative.repairs) {
      for (const { before, after } of changes) {
        if (before) affected.add(before.place_id);
        if (after) affected.add(after.place_id);
      }
    }
  }
  const sharedPlace = affected.size === 1 ? affected.values().next().value : null;
  const target = alternative.target;
  const sharedStop = !isDelay && target && alternative.repairs.every(({ changes }) =>
    changes.length === 1 && changes[0].stop_id === target.stop_id && changes[0].before) ? target : null;
  const candidates = alternative.repairs.map((repair) =>
    !isDelay && repair.action === "replace" ? repair.changes.find(({ before, after }) =>
      after && before?.stop_id === target?.stop_id && before?.place_id !== after.place_id)?.after : null);
  const firstReplacement = candidates.findIndex(Boolean);
  const timeFormatter = new Intl.DateTimeFormat(language, {
    hour: "2-digit", minute: "2-digit", timeZone: "Asia/Seoul",
    hourCycle: language === "en" ? "h12" : "h23",
  });
  const localRange = (stop) => timeFormatter.format(new Date(stop.start)) + "–" + timeFormatter.format(new Date(stop.end));

  useLayoutEffect(() => {
    const element = dialog.current;
    element.showModal();
    return () => element.close();
  }, []);

  function placeName(stop) {
    return resolvePlaceName(stop, placesById, language).name;
  }

  return (
    <dialog ref={dialog} className="stop-time-dialog guardian-alternatives" data-delay={isDelay}
      aria-labelledby={titleId}
      onKeyDown={(event) => { if (event.key === "Escape") event.stopPropagation(); }}
      onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
      <header>
        <div className="guardian-alternatives-heading">
          <h2 id={titleId}>{isDelay ? copy.delayTitle : copy.options}</h2>
          {sharedPlace && <p className="guardian-alternative-place">{placeName({ place_id: sharedPlace })}</p>}
          {sharedStop && (
            <p className="guardian-alternative-place">
              <strong className="guardian-current-label">{copy.currentStop}</strong>
              {placeName(sharedStop)} · <span>{localRange(sharedStop)}</span>
            </p>
          )}
        </div>
        <button type="button" aria-label={copy.close} disabled={busy} onClick={onClose}>×</button>
      </header>
      <div className="guardian-alternatives-body">
        {!isDelay && <Reason issue={alternative.issue} target={target} copy={copy} language={language} events={events} />}
        {error && <p role="alert">{error}</p>}
        {alternative.repairs.length === 0 && <p>{copy.noOptions}</p>}
        {alternative.repairs.map((repair, index) => {
          const remove = isDelay && repair.action === "remove";
          const timeChange = isDelay && repair.action === "move_time";
          const title = remove ? copy.delayRemove : timeChange ? copy.delayTimeChange : copy.actions[repair.action] ?? copy.apply;
          const apply = remove ? copy.delayApplyRemove : timeChange ? copy.delayApplyTime : copy.apply;
          const candidate = candidates[index];
          const expanded = openCandidate === index;
          const candidateName = candidate && placeName(candidate);
          const cardId = titleId + "-candidate-" + index;
          const after = repair.changes[0]?.after;
          const changedTime = sharedStop && after && (Date.parse(after.start) !== Date.parse(sharedStop.start) ||
            Date.parse(after.end) !== Date.parse(sharedStop.end));

          if (candidate) return (
            <Fragment key={index}>
              {index === firstReplacement && <h3 className="guardian-replacement-heading">{copy.replacementPlaces}</h3>}
              <article className="guardian-candidate">
                <button type="button" className="guardian-candidate-toggle" aria-expanded={expanded}
                  aria-controls={cardId} onClick={() => setOpenCandidate(expanded ? null : index)}>
                  <strong>{candidateName}</strong>
                  <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
                </button>
                <div id={cardId} hidden={!expanded}>
                  {expanded && (
                    <div className="chat-place-card guardian-candidate-card">
                      <PlaceCardDetails place={placesById.get(candidate.place_id) ?? candidate} name={candidateName} language={language} copy={placeCopy} />
                      {changedTime && <p className="guardian-new-time">{localRange(after)}</p>}
                      {!sharedStop && repair.changes.map(({ stop_id: id, before, after: next }) =>
                        <StandardChange key={id} before={before} after={next} placeName={placeName} range={localRange} />)}
                      <button type="button" className="guardian-apply" disabled={busy}
                        aria-label={copy.switchPlaceLabel(candidateName)} onClick={() => onApply(repair)}>{copy.switchPlace}</button>
                    </div>
                  )}
                </div>
              </article>
            </Fragment>
          );

          return (
              <article key={index}>
                <div className="guardian-repair-description">
                  <h3>{title}</h3>
                  {sharedStop ? (
                    changedTime && <p className="guardian-new-time">{localRange(after)}</p>
                  ) : repair.changes.map(({ stop_id: id, before, after }) => isDelay
                    ? <DelayChange key={id} before={before} after={after} sharedPlace={sharedPlace} placeName={placeName} />
                    : <StandardChange key={id} before={before} after={after} placeName={placeName} range={localRange} />)}
                </div>
                <button type="button" className="guardian-apply" data-secondary={remove}
                  disabled={busy} onClick={() => onApply(repair)}>{apply}</button>
              </article>
          );
        })}
      </div>
    </dialog>
  );
}
