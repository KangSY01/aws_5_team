import { useId, useLayoutEffect, useRef, useState } from "react";

const presets = [10, 20, 30];

export default function DelayForm({ copy, language, busy, loadingLabel, requestError, onRequest }) {
  const [selected, setSelected] = useState(30);
  const [custom, setCustom] = useState("");
  const [invalid, setInvalid] = useState(false);
  const input = useRef(null);
  const id = useId();
  const isCustom = selected === "custom";
  const formatter = new Intl.NumberFormat(language, { style: "unit", unit: "minute", unitDisplay: "short" });

  useLayoutEffect(() => {
    if (isCustom) input.current?.focus();
  }, [isCustom]);

  function choose(value) {
    setSelected(value);
    setInvalid(false);
  }

  function submit(event) {
    event.preventDefault();
    if (busy) return;
    const value = isCustom ? custom.trim().normalize("NFKC") : String(selected);
    const minutes = Number(value);
    if (!/^\d+$/.test(value) || minutes < 1 || minutes > 240) {
      setInvalid(true);
      input.current?.focus();
      return;
    }
    onRequest(minutes);
  }

  return (
    <form className="guardian-delay" onSubmit={submit} aria-busy={busy}>
      <p id={id}>{copy.delayQuestion}</p>
      <div className="activity-chips" role="group" aria-labelledby={id}>
        {presets.map((minutes) => (
          <button key={minutes} className="activity-chip" type="button" aria-pressed={selected === minutes}
            disabled={busy} onClick={() => choose(minutes)}>{formatter.format(minutes)}</button>
        ))}
        <button className="activity-chip" type="button" aria-pressed={isCustom} disabled={busy}
          onClick={() => choose("custom")}>{copy.delayCustom}</button>
      </div>
      {isCustom && (
        <div className="guardian-delay-custom">
          <label>
            <input ref={input} type="text" inputMode="numeric" autoComplete="off" aria-label={copy.delayMinutes}
              aria-invalid={invalid || undefined} aria-describedby={invalid ? id + "-error" : undefined}
              value={custom} disabled={busy} onChange={(event) => {
                setCustom(event.target.value);
                setInvalid(false);
              }} />
            <span aria-hidden="true">{copy.delayUnit}</span>
          </label>
          {invalid && <p id={id + "-error"} role="alert">{copy.delayInvalid}</p>}
        </div>
      )}
      {requestError && <p role="alert">{requestError}</p>}
      <button type="submit" disabled={busy}>{busy ? loadingLabel : copy.delay}</button>
    </form>
  );
}
