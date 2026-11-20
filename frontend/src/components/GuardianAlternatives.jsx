import { useLayoutEffect, useRef } from "react";
import { formatTime } from "../lib/formatTime.js";

export default function GuardianAlternatives({ alternative, copy, placesById, language, busy, error, onApply, onClose }) {
  const dialog = useRef(null);
  useLayoutEffect(() => {
    const element = dialog.current;
    element.showModal();
    return () => element.close();
  }, []);
  const placeName = (stop) => {
    const names = placesById.get(stop.place_id)?.names;
    return names?.[language] ?? names?.en ?? stop.place_id;
  };
  return (
    <dialog ref={dialog} className="stop-time-dialog guardian-alternatives" aria-labelledby="guardian-alternatives-title"
      onKeyDown={(event) => { if (event.key === "Escape") event.stopPropagation(); }}
      onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
      <header>
        <h2 id="guardian-alternatives-title">{copy.options}</h2>
        <button type="button" aria-label={copy.close} disabled={busy} onClick={onClose}>×</button>
      </header>
      {alternative.detail && <p>{alternative.detail}</p>}
      {error && <p role="alert">{error}</p>}
      {alternative.repairs.length === 0 && <p>{copy.noOptions}</p>}
      {alternative.repairs.map((repair, index) => (
        <article key={index}>
          <h3>{copy.actions[repair.action] ?? copy.apply}</h3>
          {repair.changes.map(({ stop_id: id, before, after }) => (
            <p key={id}>{before && (
              <span className={after ? undefined : "guardian-removal"}>
                {placeName(before)} · {formatTime(before.start)}–{formatTime(before.end)}
              </span>
            )}{before && after && " → "}{after &&
              <strong>{placeName(after)} · {formatTime(after.start)}–{formatTime(after.end)}</strong>}
            </p>
          ))}
          <button type="button" disabled={busy} onClick={() => onApply(repair)}>{copy.apply}</button>
        </article>
      ))}
    </dialog>
  );
}
