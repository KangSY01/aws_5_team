import { useEffect, useId, useRef } from "react";

export default function EmergencyHelp({ copy }) {
  const trigger = useRef(null);
  const dialog = useRef(null);
  const cancel = useRef(null);
  const id = useId();

  function showPrompt() {
    if (dialog.current.open) return;
    window.history.pushState({ ...window.history.state, busanEmergencyHelp: true }, "");
    dialog.current.showModal();
    cancel.current.focus({ preventScroll: true });
  }

  function dismissPrompt() {
    if (!dialog.current?.open) return;
    dialog.current.close();
    trigger.current.focus({ preventScroll: true });
  }

  function closePrompt() {
    dismissPrompt();
    if (window.history.state?.busanEmergencyHelp) {
      const { busanEmergencyHelp, ...previousState } = window.history.state;
      window.history.replaceState(previousState, "");
      window.history.back();
    }
  }

  useEffect(() => {
    function syncPrompt(event) {
      if (event.state?.busanEmergencyHelp && trigger.current.getClientRects().length > 0) {
        if (!dialog.current.open) dialog.current.showModal();
        cancel.current.focus({ preventScroll: true });
      } else {
        dismissPrompt();
      }
    }
    window.addEventListener("popstate", syncPrompt);
    return () => window.removeEventListener("popstate", syncPrompt);
  }, []);

  return (
    <>
      <button ref={trigger} className="emergency-help" type="button" aria-haspopup="dialog" onClick={showPrompt}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M10.3 4.4 2.6 18a1.8 1.8 0 0 0 1.6 2.7h15.6a1.8 1.8 0 0 0 1.6-2.7L13.7 4.4a2 2 0 0 0-3.4 0Z" />
          <path d="M12 9v4m0 3.5h.01" />
        </svg>
        <span>{copy.trigger}</span>
      </button>
      <dialog
        ref={dialog}
        className="emergency-dialog"
        aria-labelledby={`${id}-title`}
        aria-describedby={`${id}-warning ${id}-notice`}
        onCancel={(event) => {
          event.preventDefault();
          closePrompt();
        }}
      >
        <h2 id={`${id}-title`}>{copy.title}</h2>
        <p id={`${id}-warning`}>{copy.warning}</p>
        <p id={`${id}-notice`}>{copy.notice}</p>
        <div className="emergency-dialog-actions">
          <a href="tel:112">{copy.police}</a>
          <a href="tel:119">{copy.rescue}</a>
          <button ref={cancel} type="button" onClick={closePrompt}>{copy.cancel}</button>
        </div>
      </dialog>
    </>
  );
}
