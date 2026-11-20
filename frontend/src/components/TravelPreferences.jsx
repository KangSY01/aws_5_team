import { activityIds, areaIds, durationIds } from "../constants/plannerCopy.js";

export default function TravelPreferences({ value, onChange, onSubmit, onBack, busy, error, copy, backLabel }) {
  function toggle(field, id) {
    const selected = value[field];
    onChange({ ...value, [field]: selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id] });
  }

  function update(event) {
    const { name, type, value: input, checked } = event.target;
    onChange({ ...value, [name]: type === "checkbox" ? checked : input });
  }

  return (
    <form className="planner-form" onSubmit={onSubmit}>
      <small>{copy.demoCourse}</small>
      <fieldset disabled={busy}>
        <legend>{copy.stay}</legend>
        <div className="planner-options">
          {durationIds.map((id, index) => (
            <label key={id}><input type="radio" name="duration" value={id} checked={value.duration === id} onChange={update} />{copy.durations[index]}</label>
          ))}
        </div>
      </fieldset>
      <fieldset disabled={busy}>
        <legend>{copy.areas}</legend>
        <div className="planner-options">
          <button type="button" aria-pressed={!value.regions.length} onClick={() => onChange({ ...value, regions: [] })}>{copy.automatic}</button>
          {areaIds.map((id, index) => (
            <label key={id}><input type="checkbox" checked={value.regions.includes(id)} onChange={() => toggle("regions", id)} />
              <span>{copy.areasList[index]}<small>{copy.areaDetails[index]}</small></span>
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset disabled={busy}>
        <legend>{copy.interests}</legend>
        <div className="planner-options">
          {activityIds.map((id, index) => (
            <label key={id}><input type="checkbox" checked={value.activities.includes(id)} onChange={() => toggle("activities", id)} />{copy.activities[index]}</label>
          ))}
        </div>
      </fieldset>
      <details>
        <summary>{copy.options}</summary>
        <fieldset className="planner-extra" aria-label={copy.options} disabled={busy}>
          <label>{copy.food}<input name="food" value={value.food} onChange={update} maxLength={200} /></label>
          <label>{copy.transport}<input name="transport" value={value.transport} onChange={update} maxLength={100} /></label>
          <label>{copy.origin}<input name="origin" value={value.origin} onChange={update} maxLength={200} /></label>
          <label><input type="checkbox" name="less_walking" checked={value.less_walking} onChange={update} />{copy.lessWalking}</label>
          {["overnight", "long"].includes(value.duration) && (
            <label><input type="checkbox" name="lodging" checked={value.lodging} onChange={update} />{copy.lodging}</label>
          )}
        </fieldset>
      </details>
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">{copy.planning}</p>}
      <div className="planner-actions">
        <button type="button" onClick={onBack} disabled={busy}>{backLabel}</button>
        <button type="submit" disabled={busy}>{copy.makeCourse}</button>
      </div>
    </form>
  );
}
