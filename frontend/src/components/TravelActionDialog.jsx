import { useId, useLayoutEffect, useRef } from "react";

export default function TravelActionDialog({ title, closeLabel, busy, onClose, children, className = "" }) {
  const dialog = useRef(null);
  const titleId = useId();
  useLayoutEffect(() => {
    const element = dialog.current;
    element.showModal();
    return () => element.close();
  }, []);
  return (
    <dialog ref={dialog} className={`stop-time-dialog travel-action-dialog ${className}`} aria-labelledby={titleId}
      onKeyDown={(event) => { if (event.key === "Escape") event.stopPropagation(); }}
      onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
      <header>
        <h2 id={titleId}>{title}</h2>
        <button type="button" aria-label={closeLabel} disabled={busy} onClick={onClose}>×</button>
      </header>
      {children}
    </dialog>
  );
}
