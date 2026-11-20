import { useId, useLayoutEffect, useRef } from "react";
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

function StandardChange({ before, after, placeName }) {
  return (
    <p>{before && (
      <span className={after ? undefined : "guardian-removal"}>{placeName(before)} · {timeRange(before)}</span>
    )}{before && after && " → "}{after && (
      <strong>{placeName(after)} · {timeRange(after)}</strong>
    )}</p>
  );
}

export default function GuardianAlternatives({ alternative, copy, placesById, language, busy, error, onApply, onClose }) {
  const dialog = useRef(null);
  const titleId = useId();
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

  useLayoutEffect(() => {
    const element = dialog.current;
    element.showModal();
    return () => element.close();
  }, []);

  function placeName(stop) {
    const names = placesById.get(stop.place_id)?.names;
    return names?.[language] ?? names?.en ?? stop.place_id;
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
        </div>
        <button type="button" aria-label={copy.close} disabled={busy} onClick={onClose}>×</button>
      </header>
      <div className="guardian-alternatives-body">
        {alternative.detail && <p>{alternative.detail}</p>}
        {error && <p role="alert">{error}</p>}
        {alternative.repairs.length === 0 && <p>{copy.noOptions}</p>}
        {alternative.repairs.map((repair, index) => {
          const remove = isDelay && repair.action === "remove";
          const timeChange = isDelay && repair.action === "move_time";
          const title = remove ? copy.delayRemove : timeChange ? copy.delayTimeChange : copy.actions[repair.action] ?? copy.apply;
          const apply = remove ? copy.delayApplyRemove : timeChange ? copy.delayApplyTime : copy.apply;
          return (
            <article key={index}>
              <div className="guardian-repair-description">
                <h3>{title}</h3>
                {repair.changes.map(({ stop_id: id, before, after }) => isDelay
                  ? <DelayChange key={id} before={before} after={after} sharedPlace={sharedPlace} placeName={placeName} />
                  : <StandardChange key={id} before={before} after={after} placeName={placeName} />)}
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
