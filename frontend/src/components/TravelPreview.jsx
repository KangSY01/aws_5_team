import { useEffect, useRef, useState } from "react";
import { getTravelCopy, languages } from "../constants/travelCopy.js";
import EmptyState from "./EmptyState.jsx";
import samplePlan from "../mocks/sample_plan.json";
import samplePlaces from "../mocks/places.json";
import PlanList from "./PlanList.jsx";
import "./travel-preview.css";

const tabIcons = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z",
  itinerary: "M7 3v4m10-4v4M4 9h16M5 5h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zm3 8h3m2 0h3m-8 4h3",
  chat: "M20 11.5a8 8 0 0 1-8 8 9 9 0 0 1-3.4-.7L4 20l1.2-4A8 8 0 1 1 20 11.5zM8.5 11.5h7",
};
function formatDate(date, language) {
  if (!date) return null;
  const day = new Date(date + "T00:00:00Z");
  return Number.isNaN(day.getTime()) ? date : new Intl.DateTimeFormat(language, {
    dateStyle: "long", timeZone: "UTC",
  }).format(day);
}

export default function TravelPreview() {
  const [language, setLanguage] = useState("en");
  const [night, setNight] = useState(false);
  const [sheet, setSheet] = useState("closed");
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const dragStart = useRef(null);
  const root = useRef(null);
  const opener = useRef(null);
  const chatHeading = useRef(null);
  const log = useRef(null);
  const copy = getTravelCopy(language);
  const plan = messages.length ? samplePlan : null;
  const stops = plan?.stops ?? [];
  const selected = Math.max(0, stops.findIndex((stop) => stop.stop_id === selectedId));
  const open = sheet !== "closed";
  const tab = sheet === "schedule" ? "itinerary" : open ? "chat" : "home";
  const labels = { home: copy.home, itinerary: copy.itinerary, chat: copy.chat };

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const update = () => root.current?.style.setProperty("--visible-height", viewport.height + "px");
    update();
    viewport.addEventListener("resize", update);
    return () => viewport.removeEventListener("resize", update);
  }, []);

  useEffect(() => {
    if (open && log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [open, messages]);

  useEffect(() => {
    if (open) chatHeading.current?.focus();
  }, [open, tab]);

  function close() {
    setSheet("closed");
    requestAnimationFrame(() => opener.current?.focus());
  }

  function selectStop(index) {
    setSelectedId(stops[index].stop_id);
  }

  function submit(event) {
    event.preventDefault();
    const message = draft.trim();
    if (!message) return;
    setMessages((previous) => [...previous, { text: message, lang: language, role: "user" }]);
    setDraft("");

  }

  function endDrag(event) {
    if (dragStart.current === null) return;
    const distance = event.clientY - dragStart.current;
    dragStart.current = null;
    if (distance < -35 && tab === "chat") setSheet("expanded");
    if (distance > 35) {
      if (sheet === "expanded") setSheet("open");
      else close();
    }
  }

  return (
    <main ref={root} className="travel-preview" data-night={night} data-sheet={sheet} lang={language}>
      <div className="travel-shell">
        <header className="travel-header">
          <span className="travel-brand">Busan<span>Now</span></span>
          <div className="travel-controls">
            <select value={language} aria-label={copy.languageLabel} onChange={(event) => setLanguage(event.target.value)}>
              {Object.entries(languages).map(([code, name]) => <option key={code} value={code} lang={code}>{name}</option>)}
            </select>
            <button type="button" aria-label={copy.night} aria-pressed={night} onClick={() => setNight(!night)}>{night ? "☀" : "☾"}</button>
          </div>
        </header>
        {open && <button type="button" className="chat-backdrop" aria-label={copy.close} onClick={close} />}
      </div>
      <aside id="travel-chat" className="travel-chat" hidden={!open} aria-label={tab === "chat" ? copy.ask : copy.itinerary}
        onKeyDown={(event) => { if (event.key === "Escape") close(); }}>
        <div className="chat-grab" aria-hidden="true"
          onPointerDown={(event) => {
            dragStart.current = event.clientY;
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerUp={endDrag} onPointerCancel={() => { dragStart.current = null; }} />
        <header className="chat-heading">
          <h1 ref={chatHeading} tabIndex={-1}>{tab === "chat" ? copy.ask : copy.itinerary}</h1>
        </header>
        <div className="chat-content" ref={log}>
          {tab === "chat" && !messages.length && <p className="chat-intro">{copy.prompt}</p>}
          <div className="chat-messages" role="log" hidden={tab !== "chat"}>
            {messages.map((message, index) => (
              <p key={index} className="chat-bubble" data-role={message.role} lang={message.lang}>{message.text}</p>
            ))}
          </div>
          {!plan && tab === "itinerary" && <EmptyState message={copy.empty} />}
          {plan && (
            <section className="travel-panel" aria-label={copy.itinerary}>
              <h2>{copy.sampleTitle}</h2>
              {plan.date && <time dateTime={plan.date}>{formatDate(plan.date, language)}</time>}
              {stops.length ? <PlanList plan={plan} places={samplePlaces} displayLanguage={language}
                selected={selected} onSelect={selectStop} lockedLabel={copy.locked} /> : <EmptyState message={copy.empty} />}
            </section>
          )}
        </div>
        <form className="chat-compose" hidden={tab !== "chat"} onSubmit={submit}>
          <textarea aria-label={copy.messageLabel} placeholder={copy.example} rows={2}
            value={draft} onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
            }} />
          <button type="submit" disabled={!draft.trim()}>{copy.send}</button>
        </form>
      </aside>
      <nav className="travel-tabs" aria-label={copy.navigation}>
        {Object.entries(tabIcons).map(([name, path]) => (
          <button key={name} ref={name === "chat" ? opener : undefined}
            type="button" aria-label={labels[name]} title={labels[name]}
            aria-current={tab === name ? "page" : undefined}
            aria-controls={name === "home" ? undefined : "travel-chat"}
            onClick={() => setSheet(name === "home" ? "closed" : name === "itinerary" ? "schedule" : "open")}>
            <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
              strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round">
              <path d={path} />
            </svg>
          </button>
        ))}
      </nav>
    </main>
  );
}
