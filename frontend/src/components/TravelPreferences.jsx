import { useEffect, useRef, useState } from "react";
import { durationIds, foodPreferenceIds, transportPreferenceIds } from "../constants/plannerCopy.js";
import { activityGroups, activityIcons, activityTextKey, availableActivities, normalizeActivities } from "../lib/activityPreferences.js";
import { RegionChoices } from "./RegionMap.jsx";

function PreferenceTextChips({ items, knownLabels, onChange, copy, busy }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const input = useRef(null);
  const editor = useRef(null);
  const entered = draft.trim().replace(/\s+/g, " ");
  const key = activityTextKey(entered);
  const duplicate = key && [...items, ...knownLabels].some((item) => activityTextKey(item) === key);

  useEffect(() => {
    if (!editing) return;
    const viewport = window.visualViewport;
    let frame;
    function revealEditor() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => editor.current?.scrollIntoView?.({ block: "nearest" }));
    }
    input.current?.focus({ preventScroll: true });
    revealEditor();
    viewport?.addEventListener("resize", revealEditor);
    return () => {
      cancelAnimationFrame(frame);
      viewport?.removeEventListener("resize", revealEditor);
    };
  }, [editing]);

  function add() {
    if (!key || duplicate || busy) return;
    onChange([...items, entered]);
    setDraft("");
    setEditing(false);
  }

  return (
    <>
      {items.length > 0 && (
        <div className="activity-chips">
          {items.map((item) => (
            <button key={item} type="button" className="activity-chip activity-custom-chip"
              aria-label={copy.removeCustom + " · " + item}
              onClick={() => onChange(items.filter((value) => value !== item))}>
              <span>{item}</span><span aria-hidden="true">×</span>
            </button>
          ))}
        </div>
      )}
      {!editing ? (
        <button type="button" className="activity-chip activity-custom-open" onClick={() => setEditing(true)}>
          <span aria-hidden="true">＋</span><span>{copy.openCustom}</span>
        </button>
      ) : (
        <div ref={editor} className="activity-custom-editor">
          <div className="activity-custom-input">
            <span aria-hidden="true">＋</span>
            <input ref={input} aria-label={copy.customLabel} placeholder={copy.customLabel} value={draft} maxLength={60}
              onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
                if (event.key !== "Enter") return;
                event.preventDefault();
                if (!event.nativeEvent.isComposing) add();
              }} />
          </div>
          <button type="button" disabled={!key || Boolean(duplicate)} onClick={add}>{copy.addCustom}</button>
          {duplicate && <small role="status">{copy.duplicate}</small>}
        </div>
      )}
    </>
  );
}

export default function TravelPreferences({ value, onChange, onSubmit, onBack, busy, error, copy, backLabel, onShowRegions }) {
  const [durationMissing, setDurationMissing] = useState(false);
  const durationQuestion = useRef(null);
  const selected = normalizeActivities(value.activities);
  const { groups, keywords } = copy.activityCopy;

  function chip(id) {
    const active = selected.includes(id);
    return (
      <button key={id} type="button" className="activity-chip" aria-pressed={active}
        onClick={() => onChange({ ...value, activities: active ? selected.filter((item) => item !== id) : [...selected, id] })}>
        <span className="activity-chip-icon" aria-hidden="true">{activityIcons[id]}</span>
        <span>{keywords[id]}</span>
      </button>
    );
  }

  function update(event) {
    const { name, type, value: input, checked } = event.target;
    if (name === "duration") setDurationMissing(false);
    onChange({ ...value, [name]: type === "checkbox" ? checked : input });
  }

  function submit(event) {
    if (durationIds.includes(value.duration)) {
      onSubmit(event);
      return;
    }
    event.preventDefault();
    setDurationMissing(true);
    durationQuestion.current?.scrollIntoView?.({ block: "nearest" });
    durationQuestion.current?.querySelector("input")?.focus({ preventScroll: true });
  }

  const optional = <span className="planner-answer-type">{copy.optionalAnswer}</span>;

  return (
    <form className="planner-form" noValidate onSubmit={submit}>
      <fieldset ref={durationQuestion} className="duration-section" disabled={busy}>
        <legend>{copy.stay} <span className="planner-answer-type planner-answer-required">{copy.requiredAnswer}</span></legend>
        <div className="activity-chips">
          {durationIds.map((id, index) => (
            <label key={id} className="activity-chip duration-chip">
              <input type="radio" name="duration" value={id} checked={value.duration === id} onChange={update} required
                aria-invalid={durationMissing || undefined} aria-describedby={durationMissing ? "planner-duration-error" : undefined} />
              <span>{copy.durations[index]}</span>
            </label>
          ))}
        </div>
        {durationMissing && <p id="planner-duration-error" className="planner-duration-error" role="alert">{copy.durationRequired}</p>}
      </fieldset>
      <label className="planner-start-time">
        <span>{copy.tripStart} {optional}</span>
        <input type="time" name="startTime" value={value.startTime ?? ""} onChange={update} disabled={busy} />
      </label>
      <fieldset className="region-section" disabled={busy}>
        <legend>{copy.areas} {optional}</legend>
        <RegionChoices selected={value.regions} onChange={(regions) => onChange({ ...value, regions })} copy={copy} />
        <button className="activity-chip region-show-map" type="button" onClick={onShowRegions}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
            strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Zm6-3v15m6-12v15" />
          </svg>
          <span>{value.regions.length ? copy.changeAreas : copy.showAreas}</span>
        </button>
      </fieldset>
      <fieldset className="activity-section" disabled={busy}>
        <legend>{copy.interests} {optional}</legend>
        <div className="activity-groups">
          {activityGroups.map(([group, ids]) => {
            const choices = ids.filter((id) => availableActivities.has(id));
            if (!choices.length) return null;
            return (
              <section key={group} aria-labelledby={`activity-group-${group}`}>
                <h3 id={`activity-group-${group}`}>{groups[group]}</h3>
                <div className="activity-chips">{choices.map(chip)}</div>
              </section>
            );
          })}
        </div>
        <PreferenceTextChips items={value.customActivities ?? []}
          knownLabels={[...availableActivities].map((id) => keywords[id])}
          onChange={(customActivities) => onChange({ ...value, customActivities })}
          copy={copy.activityCopy} busy={busy} />
      </fieldset>
      <fieldset className="food-section" disabled={busy}>
        <legend>{copy.food} {optional}</legend>
        <div className="activity-chips">
          {foodPreferenceIds.map((id) => {
            const active = value.foodTags.includes(id);
            return (
              <button key={id} type="button" className="activity-chip" aria-pressed={active}
                onClick={() => onChange({ ...value, foodTags: active
                  ? value.foodTags.filter((tag) => tag !== id) : [...value.foodTags, id] })}>
                {copy.foodLabels[id]}
              </button>
            );
          })}
        </div>
        <PreferenceTextChips items={value.customFoods} knownLabels={Object.values(copy.foodLabels)}
          onChange={(customFoods) => onChange({ ...value, customFoods })} copy={copy.foodEditor} busy={busy} />
      </fieldset>
      <fieldset className="transport-section" disabled={busy}>
        <legend>{copy.transport} {optional}</legend>
        <div className="activity-chips">
          {transportPreferenceIds.map((id) => (
            <label key={id} className="activity-chip duration-chip">
              <input type="radio" name="transport" value={id} checked={value.transport === id} onChange={update} />
              <span>{copy.transportLabels[id]}</span>
            </label>
          ))}
        </div>
        <button type="button" className="activity-chip walking-preference" aria-pressed={value.less_walking}
          onClick={() => onChange({ ...value, less_walking: !value.less_walking })}>{copy.lessWalking}</button>
      </fieldset>
      {["overnight", "long"].includes(value.duration) && (
        <fieldset className="planner-extra" disabled={busy}>
          <legend>{copy.lodging} {optional}</legend>
          <label><input type="checkbox" name="lodging" checked={value.lodging} onChange={update} /> {copy.lodging}</label>
        </fieldset>
      )}
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">{copy.planning}</p>}
      <div className="planner-actions">
        <button type="button" onClick={onBack} disabled={busy}>{backLabel}</button>
        <button type="submit" disabled={busy}>{copy.makeCourse}</button>
      </div>
    </form>
  );
}
