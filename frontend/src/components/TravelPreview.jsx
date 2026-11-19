import { useEffect, useRef, useState } from "react";
import { getTravelCopy, languages } from "../constants/travelCopy.js";
import koreanFlag from "../assets/flags/kr.svg";
import englishFlag from "../assets/flags/gb.svg";
import japaneseFlag from "../assets/flags/jp.svg";
import simplifiedChineseFlag from "../assets/flags/cn.svg";
import traditionalChineseFlag from "../assets/flags/tw.svg";
import EmptyState from "./EmptyState.jsx";
import samplePlan from "../mocks/sample_plan.json";
import samplePlaces from "../mocks/places.json";
import BusanMap from "./BusanMap.jsx";
import PlanList from "./PlanList.jsx";
import "./travel-preview.css";

const localeFlags = {
  ko: koreanFlag,
  en: englishFlag,
  ja: japaneseFlag,
  "zh-Hans": simplifiedChineseFlag,
  "zh-Hant": traditionalChineseFlag,
};

const tabIcons = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z",
  itinerary: "M7 3v4m10-4v4M4 9h16M5 5h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zm3 8h3m2 0h3m-8 4h3",
  chat: "M20 11.5a8 8 0 0 1-8 8 9 9 0 0 1-3.4-.7L4 20l1.2-4A8 8 0 1 1 20 11.5zM8.5 11.5h7",
  profile: "M16 8a4 4 0 1 1-8 0 4 4 0 0 1 8 0ZM4 21v-2a4 4 0 0 1 4-4h8a4 4 0 0 1 4 4v2",
};
function LanguageTrigger({ className, label }) {
  return (
    <button type="button" className={className} popoverTarget="travel-language-menu" aria-label={label}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <ellipse cx="12" cy="12" rx="4" ry="9" />
        <path d="M3 12h18" />
      </svg>
    </button>
  );
}

const languageStorageKey = "busannow.language";

function getSavedLanguage() {
  try {
    const saved = window.localStorage.getItem(languageStorageKey);
    if (Object.hasOwn(languages, saved)) return saved;
  } catch {
    // Storage can be unavailable in private or restricted contexts.
  }
  return "en";
}

function LanguageOptions({ language, onSelect }) {
  return Object.entries(languages).map(([code, name]) => (
    <button key={code} type="button" lang={code} aria-pressed={language === code} onClick={() => onSelect(code)}>
      <img className="travel-language-flag" src={localeFlags[code]} alt="" width="16" height="16" />
      <span className="travel-language-name">{name}</span>
      {language === code && (
        <svg className="travel-language-check" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="m5 12 4 4L19 6" />
        </svg>
      )}
    </button>
  ));
}

function ProfilePage({ copy, language, onLanguageChange }) {
  const [languageOpen, setLanguageOpen] = useState(false);
  const heading = useRef(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, []);

  return (
    <section id="travel-profile" className="travel-profile" aria-labelledby="profile-heading">
      <div className="profile-content">
        <header>
          <h1 id="profile-heading" ref={heading} tabIndex={-1}>{copy.profile}</h1>
          <p>{copy.guest}</p>
        </header>
        <div className="profile-settings">
          <button type="button" className="profile-language-row" aria-expanded={languageOpen}
            aria-controls="profile-languages" onClick={() => setLanguageOpen(!languageOpen)}>
            <span>{copy.languageLabel}</span>
            <span className="profile-language-value" lang={language}>{languages[language]}</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m6 9 6 6 6-6" />
            </svg>
          </button>
          <div id="profile-languages" className="profile-language-options" hidden={!languageOpen}
            role="group" aria-label={copy.languageLabel}>
            <LanguageOptions language={language} onSelect={onLanguageChange} />
          </div>
          <section className="profile-account">
            <h2>{copy.account}</h2>
            <p>{copy.accountUnavailable}</p>
          </section>
        </div>
      </div>
    </section>
  );
}

function formatDate(date, language) {
  if (!date) return null;
  const day = new Date(date + "T00:00:00Z");
  return Number.isNaN(day.getTime()) ? date : new Intl.DateTimeFormat(language, {
    dateStyle: "long", timeZone: "UTC",
  }).format(day);
}

export default function TravelPreview({ night = false } = {}) {
  const [language, setLanguage] = useState(getSavedLanguage);
  const [profile, setProfile] = useState(() => window.location.hash === "#profile");
  const [open, setOpen] = useState(false);
  const [panel, setPanel] = useState("chat");
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState([]);
  const [selectedId, setSelectedId] = useState(samplePlan.stops[0]?.stop_id ?? null);
  const [mapFocus, setMapFocus] = useState(null);
  const dragStart = useRef(null);
  const root = useRef(null);
  const tabBar = useRef(null);
  const chatHeading = useRef(null);
  const log = useRef(null);
  const composer = useRef(null);
  const languageMenu = useRef(null);
  const copy = getTravelCopy(language);
  const languageLabel = copy.languageLabel + ": " + languages[language];
  const plan = samplePlan;
  const stops = plan.stops;
  const selected = Math.max(0, stops.findIndex((stop) => stop.stop_id === selectedId));
  const tab = profile ? "profile" : open ? panel : "home";
  const showChat = panel === "chat";
  const collapseLabel = showChat ? copy.collapse : copy.collapseItinerary;
  const closeLabel = showChat ? copy.close : copy.closeItinerary;
  const labels = { home: copy.home, itinerary: copy.itinerary, chat: copy.chat, profile: copy.profile };

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

  useEffect(() => {
    function syncPage() {
      const next = window.location.hash === "#profile";
      setProfile(next);
      if (next) {
        setOpen(false);
        setExpanded(false);
      }
    }
    window.addEventListener("popstate", syncPage);
    window.addEventListener("hashchange", syncPage);
    return () => {
      window.removeEventListener("popstate", syncPage);
      window.removeEventListener("hashchange", syncPage);
    };
  }, []);

  function changeLanguage(code) {
    setLanguage(code);
    try {
      window.localStorage.setItem(languageStorageKey, code);
    } catch {
      // The selected language still applies for the current session.
    }
  }

  function navigateProfile(next) {
    if (profile === next) return;
    const { pathname, search } = window.location;
    window.history.pushState(null, "", pathname + search + (next ? "#profile" : ""));
    setProfile(next);
  }

  function close() {
    setOpen(false);
    setExpanded(false);
    tabBar.current?.querySelector(`[data-tab="${panel}"]`)?.focus();
  }

  function selectStop(index) {
    const id = stops[index].stop_id;
    setSelectedId(id);
    setMapFocus({ id });
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
    <main ref={root} className="travel-preview" data-night={night} data-page={profile ? "profile" : "map"} data-sheet={open ? "open" : "closed"} data-expanded={expanded} lang={language}>
      <div className="travel-shell" inert={profile} aria-hidden={profile}>
        <BusanMap plan={plan} places={samplePlaces} language={language} label={copy.map}
          selectedId={selectedId} onSelect={setSelectedId} focusRequest={mapFocus} />
        <header className="travel-header">
          <span className="travel-brand">Busan<span>Now</span></span>
          <LanguageTrigger className="travel-language-trigger" label={languageLabel} />
          <div id="travel-language-menu" className="travel-language-menu" ref={languageMenu}
            popover="auto" role="group" aria-label={copy.languageLabel}>
            <LanguageOptions language={language} onSelect={(code) => {
              changeLanguage(code);
              languageMenu.current.hidePopover();
            }} />
          </div>
        </header>
      </div>
      {profile && <ProfilePage copy={copy} language={language} onLanguageChange={changeLanguage} />}
      <aside id="travel-chat" className="travel-chat" hidden={!open} inert={!open} aria-hidden={!open} aria-labelledby="travel-panel-title"
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

          {(!showChat || messages.length > 0) && (
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
            aria-controls={name === "chat" || name === "itinerary" ? "travel-chat" : undefined}
            aria-expanded={name === "chat" || name === "itinerary" ? tab === name : undefined}
            onClick={() => {
              if (name === "profile") {
                setOpen(false);
                setExpanded(false);
                navigateProfile(true);
                return;
              }
              navigateProfile(false);
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
