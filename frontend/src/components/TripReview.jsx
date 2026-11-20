import { useState } from "react";
import TravelActionDialog from "./TravelActionDialog.jsx";

// 여행 종료 평가: 루트 요약(방문 수, 이동 시간, 혼잡 장소) + 별점 + 빠른 태그
// summary: { visited, total, walkMinutes, transitMinutes, crowded }
export default function TripReview({ copy, summary, onSave, onSkip, onClose }) {
  const [rating, setRating] = useState(0);
  const [tags, setTags] = useState([]);
  const travel = summary.walkMinutes + summary.transitMinutes;
  const toggleTag = (tag) => setTags((current) => current.includes(tag) ? current.filter((item) => item !== tag) : [...current, tag]);
  return (
    <TravelActionDialog title={copy.title} closeLabel={copy.close} className="trip-review-dialog" onClose={onClose}>
      <ul className="trip-review-summary">
        <li>{copy.visited(summary.visited, summary.total)}</li>
        {travel > 0 && <li>{copy.travel(travel)}
          <small>{[summary.walkMinutes > 0 && copy.walk(summary.walkMinutes), summary.transitMinutes > 0 && copy.transit(summary.transitMinutes)]
            .filter(Boolean).join(" · ")}</small></li>}
        <li>{summary.crowded ? copy.crowded(summary.crowded) : copy.noCrowd}</li>
      </ul>
      <fieldset className="trip-review-rating">
        <legend>{copy.rating}</legend>
        {[1, 2, 3, 4, 5].map((value) => (
          <button key={value} type="button" aria-label={copy.star(value)} aria-pressed={rating === value}
            data-filled={value <= rating || undefined} onClick={() => setRating(value)}>★</button>
        ))}
      </fieldset>
      <fieldset className="trip-review-tags">
        <legend>{copy.tagsLabel}</legend>
        {copy.tags.map((tag) => (
          <button key={tag} type="button" aria-pressed={tags.includes(tag)} onClick={() => toggleTag(tag)}>{tag}</button>
        ))}
      </fieldset>
      <div className="stop-time-actions">
        <button type="button" onClick={onSkip}>{copy.skip}</button>
        <button type="button" className="trip-review-save" disabled={!rating} onClick={() => onSave({ rating, tags, ...summary })}>{copy.save}</button>
      </div>
    </TravelActionDialog>
  );
}
