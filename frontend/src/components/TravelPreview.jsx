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

export default function TravelPreview({ night = false } = {}) {
  const [language, setLanguage] = useState("en");
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState("chat");
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const dragStart = useRef(null);
  const root = useRef(null);
  const tabBar = useRef(null);
  const chatHeading = useRef(null);
  const log = useRef(null);
  const composer = useRef(null);
  const languageMenu = useRef(null);
  const copy = getTravelCopy(language);
  const plan = messages.length ? samplePlan : null;
  const stops = plan?.stops ?? [];
  const selected = Math.max(0, stops.findIndex((stop) => stop.stop_id === selectedId));
  const tab = open ? panel : "home";
  const showChat = panel === "chat";
  const collapseLabel = showChat ? copy.collapse : copy.collapseItinerary;
  const closeLabel = showChat ? copy.close : copy.closeItinerary;
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
  }, [open, messages, tab]);

  useEffect(() => {
    if (open) chatHeading.current?.focus();
  }, [open, tab]);

  function close() {
    setOpen(false);
    setExpanded(false);
    tabBar.current?.querySelector(`[data-tab="${panel}"]`)?.focus();
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
    if (distance < -35) setExpanded(true);
    if (distance > 35) {
      if (expanded) setExpanded(false);
      else close();
    }
  }

  return (
    <main ref={root} className="travel-preview" data-night={night} data-sheet={open ? "open" : "closed"} data-expanded={expanded} lang={language}>
      <div className="travel-shell">
        <header className="travel-header">
          <span className="travel-brand">Busan<span>Now</span></span>
          <button type="button" className="travel-language-trigger" popoverTarget="travel-language-menu"
            aria-label={copy.languageLabel + ": " + languages[language]}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
              <ellipse cx="12" cy="12" rx="4" ry="9" />
              <path d="M3 12h18" />
            </svg>
          </button>
          <div id="travel-language-menu" className="travel-language-menu" ref={languageMenu}
            popover="auto" role="group" aria-label={copy.languageLabel}>
            {Object.entries(languages).map(([code, name]) => (
              <button key={code} type="button" lang={code} aria-pressed={language === code}
                onClick={() => {
                  setLanguage(code);
                  languageMenu.current.hidePopover();
                }}>
                {name}
                {language === code && <span aria-hidden="true">✓</span>}
              </button>
            ))}
          </div>
        </header>
        {open && <button type="button" className="chat-backdrop" aria-label={closeLabel} tabIndex={-1} onClick={close} />}
      </div>
      <aside id="travel-chat" className="travel-chat" hidden={!open} inert={!open} aria-labelledby="travel-panel-title"
        onKeyDown={(event) => { if (event.key === "Escape") close(); }}>
        <div className="chat-grab" aria-hidden="true"
          onPointerDown={(event) => {
            dragStart.current = event.clientY;
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerUp={endDrag} onPointerCancel={() => { dragStart.current = null; }} />
        <header className="chat-heading">
          <h1 id="travel-panel-title" ref={chatHeading} tabIndex={-1}>{showChat ? "Busan AI" : copy.itinerary}</h1>
          <button type="button" className="chat-collapse" aria-label={collapseLabel} onClick={close}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
          </button>
          <button type="button" className="chat-close" aria-label={closeLabel} onClick={close}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
          </button>
        </header>
        <div className="chat-content" ref={log}>
          <div className="chat-messages" role="log" hidden={!showChat}>
            <p className="chat-bubble">{copy.greeting}</p>
            {!messages.length && (
              <div className="chat-suggestions">
                {copy.suggestions.map((question) => (
                  <button key={question} type="button" aria-pressed={draft === question} onClick={() => {
                    setDraft(question);
                    composer.current?.focus();
                  }}>{question}</button>
                ))}
              </div>
            )}
            {messages.map((message, index) => (
              <p key={index} className="chat-bubble" data-role={message.role} lang={message.lang}>{message.text}</p>
            ))}
          </div>
          {!plan && !showChat && <EmptyState message={copy.empty} />}
          {plan && (
            <section className="travel-panel" aria-label={copy.itinerary}>
              <h2>{copy.sampleTitle}</h2>
              {plan.date && <time dateTime={plan.date}>{formatDate(plan.date, language)}</time>}
              {stops.length ? <PlanList plan={plan} places={samplePlaces} displayLanguage={language}
                selected={selected} onSelect={selectStop} lockedLabel={copy.locked} /> : <EmptyState message={copy.empty} />}
            </section>
          )}
        </div>
        <form className="chat-compose" hidden={!showChat} onSubmit={submit}>
          <textarea ref={composer} aria-label={copy.messageLabel} placeholder={copy.placeholder} rows={1}
            value={draft} onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
            }} />
          <button type="submit" aria-label={copy.send} disabled={!draft.trim()}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6" /></svg>
          </button>
        </form>
      </aside>
      <nav ref={tabBar} className="travel-tabs" data-active-tab={tab} aria-label={copy.navigation}>
        <span className="travel-tab-indicator" aria-hidden="true" />
        {Object.entries(tabIcons).map(([name, path]) => (
          <button key={name} data-tab={name}
            type="button" aria-label={labels[name]} title={labels[name]}
            aria-current={tab === name ? "page" : undefined}
            aria-controls={name === "home" ? undefined : "travel-chat"}
            aria-expanded={name !== "home" ? tab === name : undefined}
            onClick={() => {
              if (name === "home") {
                setOpen(false);
                setExpanded(false);
              } else if (tab === name) {
                close();
              } else {
                setPanel(name);
                setOpen(true);
              }
            }}>
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
