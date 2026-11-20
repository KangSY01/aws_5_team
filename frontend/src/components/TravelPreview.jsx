import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getTravelCopy, languages } from "../constants/travelCopy.js";
import { getPlannerCopy, transportPreferenceIds } from "../constants/plannerCopy.js";
import { recommendDemo, suggestDemo } from "../lib/demoPlanner.js";
import { normalizeActivities } from "../lib/activityPreferences.js";
import koreanFlag from "../assets/flags/kr.svg";
import englishFlag from "../assets/flags/gb.svg";
import japaneseFlag from "../assets/flags/jp.svg";
import simplifiedChineseFlag from "../assets/flags/cn.svg";
import traditionalChineseFlag from "../assets/flags/tw.svg";
import EmptyState from "./EmptyState.jsx";
import sampleEvents from "../mocks/events.js";
import { buildPlacesById, resolvePlaceName } from "../lib/resolvePlaceName.js";
import BusanMap from "./BusanMap.jsx";
import PlanList from "./PlanList.jsx";
import TravelPreferences from "./TravelPreferences.jsx";
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
const activeTripStorageKey = "busannow.activeTrip";
const courseStorageKey = "busannow.course";
const preferencesStorageKey = "busannow.preferences";
const emptyPlan = { stops: [] };
const emptyPlaces = [];
const defaultPreferences = {
  duration: "day", regions: [], activities: [], customActivities: [], foodTags: [], customFoods: [],
  transport: "", less_walking: false, lodging: false,
};

function loadSaved(key) {
  try {
    return JSON.parse(window.localStorage.getItem(key));
  } catch {
    return null;
  }
}

function loadPreferences() {
  const { food, origin, ...saved } = loadSaved(preferencesStorageKey) ?? {};
  const values = { ...defaultPreferences, ...saved };
  if (typeof food === "string" && food.trim() && !values.customFoods.length) values.customFoods = [food.trim()];
  if (!transportPreferenceIds.includes(values.transport)) {
    const previous = values.transport;
    values.transport = /대중교통|지하철|버스|transit|subway|metro|\bbus\b|公共交通|大眾運輸/iu.test(previous) ? "public_transit"
      : /차량|자동차|택시|\bcar\b|taxi|汽車|汽车/iu.test(previous) ? "car"
      : /도보|걷기|walk|徒歩|步行/iu.test(previous) ? "walking"
      : /상관없|no preference|こだわらない|无偏好|無偏好/iu.test(previous) ? "any" : "";
  }
  return values;
}

function save(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // The session still works when browser storage is unavailable.
  }
}

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

function ProfilePage({ copy, plannerCopy, language, onLanguageChange }) {
  const [languageOpen, setLanguageOpen] = useState(false);
  const heading = useRef(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, []);

  return (
    <section id="travel-profile" className="travel-profile" aria-labelledby="profile-heading">
      <div className="profile-content">
        <header>
          <h1 id="profile-heading" ref={heading} tabIndex={-1}>{copy.profile}</h1>
          <p>{plannerCopy.demoAccount}</p>
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
  const [course, setCourse] = useState(() => {
    const saved = loadSaved(courseStorageKey);
    return Array.isArray(saved?.plan?.stops) && Array.isArray(saved?.places) ? saved : null;
  });
  const [tripStarted, setTripStarted] = useState(() => {
    try {
      return Boolean(course && window.localStorage.getItem(activeTripStorageKey) === course.plan.plan_id);
    } catch {
      return false;
    }
  });
  const [preferences, setPreferences] = useState(loadPreferences);
  const [showPreferences, setShowPreferences] = useState(false);
  const [event, setEvent] = useState(null);
  const [regionDraft, setRegionDraft] = useState(null);
  const regionSession = useRef(null);
  const restorePreferencesScroll = useRef(null);
  const [editId, setEditId] = useState(null);
  const [reviewStatus, setReviewStatus] = useState(null);
  const [planError, setPlanError] = useState(null);
  const [pending, setPending] = useState(null);
  const requestInProgress = useRef(false);
  const [panel, setPanel] = useState("chat");
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState([]);
  const [selectedId, setSelectedId] = useState(() => course?.plan.stops[0]?.stop_id ?? null);
  const [mapFocus, setMapFocus] = useState(null);
  const dragStart = useRef(null);
  const root = useRef(null);
  const tabBar = useRef(null);
  const chatHeading = useRef(null);
  const log = useRef(null);
  const composer = useRef(null);
  const languageMenu = useRef(null);
  const copy = getTravelCopy(language);
  const plannerCopy = getPlannerCopy(language);
  const languageLabel = copy.languageLabel + ": " + languages[language];
  const plan = course?.plan ?? emptyPlan;
  const places = course?.places ?? emptyPlaces;
  const placesById = useMemo(() => buildPlacesById(places), [places]);
  const stops = plan.stops;
  const nextStop = tripStarted ? stops[0] : null;
  const nextPlace = nextStop ? resolvePlaceName(nextStop, placesById, language).name : null;
  const editIndex = stops.findIndex((stop) => stop.stop_id === editId);
  const editStop = stops[editIndex];
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
    if (open && tab === "chat" && log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [open, messages, tab, pending, reviewStatus]);

  useEffect(() => {
    if (tab === "itinerary" && log.current) {
      log.current.scrollTop = restorePreferencesScroll.current ?? 0;
      restorePreferencesScroll.current = null;
    }
  }, [tab, showPreferences]);

  useEffect(() => {
    if (open) chatHeading.current?.focus({ preventScroll: true });
  }, [open, tab]);

  const exitRegionPicker = useCallback((restorePanel) => {
    if (!regionSession.current) return;
    const { scroll, expanded: wasExpanded } = regionSession.current;
    regionSession.current = null;
    setRegionDraft(null);
    if (restorePanel) {
      restorePreferencesScroll.current = scroll;
      setPanel("itinerary");
      setExpanded(wasExpanded);
      setOpen(true);
    }
  }, []);

  useEffect(() => {
    function syncPage() {
      const next = window.location.hash === "#profile";
      if (!window.history.state?.busanRegionPicker) exitRegionPicker(!next);
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
  }, [exitRegionPicker]);

  function showRegions() {
    if (regionSession.current) return;
    regionSession.current = { scroll: log.current?.scrollTop ?? 0, expanded };
    window.history.pushState({ ...window.history.state, busanRegionPicker: true }, "");
    setRegionDraft([...preferences.regions]);
    setEvent(null);
    setExpanded(false);
    setOpen(false);
  }

  function finishRegions(commit) {
    if (!regionSession.current) return;
    if (commit) updatePreferences({ ...preferences, regions: regionDraft });
    exitRegionPicker(true);
    if (window.history.state?.busanRegionPicker) {
      const { busanRegionPicker, ...previousHistoryState } = window.history.state;
      window.history.replaceState(previousHistoryState, "");
      window.history.back();
    }
  }

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

  function changeTrip(active, closePanel = true) {
    if (active && !stops.length) return;
    setTripStarted(active);
    try {
      if (active) window.localStorage.setItem(activeTripStorageKey, plan.plan_id);
      else window.localStorage.removeItem(activeTripStorageKey);
    } catch {
      // Travel mode remains available in the current session without storage.
    }
    if (closePanel) {
      setOpen(false);
      setExpanded(false);
      tabBar.current?.querySelector('[data-tab="home"]')?.focus();
    }
    if (active) {
      setSelectedId(stops[0].stop_id);
      setMapFocus({ id: stops[0].stop_id });
    }
  }

  function selectStop(index) {
    const id = stops[index].stop_id;
    setSelectedId(id);
    setMapFocus({ id });
  }

  function updatePreferences(next) {
    setPreferences(next);
    save(preferencesStorageKey, next);
  }

  async function recommendCourse(event) {
    event.preventDefault();
    if (requestInProgress.current) return;
    const { foodTags, customFoods, ...answers } = preferences;
    const values = { ...answers, activities: normalizeActivities(preferences.activities), food: [...foodTags, ...customFoods].join(", "),
      lodging: ["overnight", "long"].includes(preferences.duration) && preferences.lodging };
    requestInProgress.current = true;
    setPending("recommend");
    setPlanError(null);
    try {
      const result = await recommendDemo(values, language);
      if (!result?.plan?.plan_id || !result.plan.stops?.length || !Array.isArray(result.places)) throw new Error();
      const next = { ...result, preferences: values };
      setCourse(next);
      save(courseStorageKey, next);
      if (tripStarted) changeTrip(false, false);
      setSelectedId(result.plan.stops[0].stop_id);
      setMapFocus(null);
      setEditId(null);
      setShowPreferences(false);
    } catch (error) {
      setPlanError(error.message === "noPlaces" ? "noPlaces" : "requestFailed");
    } finally {
      requestInProgress.current = false;
      setPending(null);
    }
  }

  function openEdit(index) {
    setEditId(stops[index].stop_id);
    setReviewStatus(null);
    setPanel("chat");
  }

  async function submit(event) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || !editStop || editStop.locked || requestInProgress.current) return;
    requestInProgress.current = true;
    setPending("edit");
    setReviewStatus(null);
    setMessages((previous) => [...previous, { text: message, lang: language, role: "user" }]);
    setDraft("");
    try {
      const result = await suggestDemo({
        plan, stop_id: editId, preferences: course.preferences, message, language,
      });
      if ((!result?.place && !result?.reason_code) ||
        (result.place && (!Number.isFinite(result.place.lat) || !Number.isFinite(result.place.lng) ||
          typeof result.place.place_id !== "string" || stops.some((stop) => stop.place_id === result.place.place_id)))) {
        throw new Error();
      }
      setMessages((previous) => [...previous, {
        result, lang: language, snapshot: course, target: editStop, index: editIndex,
      }]);
    } catch {
      setDraft((current) => current || message);
      setReviewStatus("requestFailed");
    } finally {
      requestInProgress.current = false;
      setPending(null);
    }
  }

  function applySuggestion(message) {
    if (requestInProgress.current) return;
    if (message.snapshot !== course) {
      setReviewStatus("stale");
      return;
    }
    const { place } = message.result;
    const next = {
      ...course,
      plan: { ...plan, stops: stops.map((stop) => stop === message.target ? { ...stop, place_id: place.place_id } : stop) },
      places: [...places.filter((item) => item.place_id !== place.place_id), place],
    };
    setCourse(next);
    save(courseStorageKey, next);
    setSelectedId(message.target.stop_id);
    setMapFocus({ id: message.target.stop_id });
    setMessages((previous) => previous.map((entry) => entry === message ? { ...entry, applied: true } : entry));
    setReviewStatus("applied");
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
    <main ref={root} className="travel-preview" data-night={night} data-page={profile ? "profile" : "map"} data-sheet={open ? "open" : "closed"} data-expanded={expanded}
      data-compact-itinerary={!showChat && !showPreferences && !stops.length} data-region-picker={regionDraft !== null} lang={language}>
      <div className="travel-shell" inert={profile} aria-hidden={profile}>
        <BusanMap plan={plan} places={places} events={sampleEvents} onEventSelect={setEvent}
          language={language} label={copy.map}
          selectedId={selectedId} nextStopId={nextStop?.stop_id} onSelect={setSelectedId} focusRequest={mapFocus}
          regionPicker={regionDraft && {
            selected: regionDraft, onChange: setRegionDraft, copy: plannerCopy,
            onDone: () => finishRegions(true), onCancel: () => finishRegions(false),
          }} />
        <header className="travel-header">
          <div className="travel-brand-group">
            <span className="travel-brand">Busan<span>Now</span></span>
            {tripStarted && <span className="trip-status">{copy.traveling}</span>}
          </div>
          <LanguageTrigger className="travel-language-trigger" label={languageLabel} />
          <div id="travel-language-menu" className="travel-language-menu" ref={languageMenu}
            popover="auto" role="group" aria-label={copy.languageLabel}>
            <LanguageOptions language={language} onSelect={(code) => {
              changeLanguage(code);
              languageMenu.current.hidePopover();
            }} />
          </div>
        </header>
        {tab === "home" && event && (
          <section className="map-event-card" aria-label={event.names[language]}>
            <button type="button" aria-label={plannerCopy.closeEvent} onClick={() => setEvent(null)}>×</button>
            <small>{plannerCopy.sampleEvent}</small>
            <h2>{event.names[language]}</h2>
            <p>{formatDate(event.from, language)}{event.from !== event.to && " – " + formatDate(event.to, language)}</p>
            <p>{event.place.names[language] ?? event.place.names.en}</p>
          </section>
        )}
      </div>
      {tab === "home" && !regionDraft && nextPlace && (
        <div className="trip-next">
          <span>{copy.nextPlace}</span>
          <strong>{nextPlace}</strong>
        </div>
      )}
      {profile && <ProfilePage copy={copy} plannerCopy={plannerCopy} language={language} onLanguageChange={changeLanguage} />}
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
            {!editStop && <p className="chat-bubble">{plannerCopy.pickStop}</p>}
            {messages.map((message, index) => {
              if (!message.result) return <p key={index} className="chat-bubble" data-role={message.role} lang={message.lang}>{message.text}</p>;
              const { result, target, snapshot } = message;
              const original = snapshot.places.find((place) => place.place_id === target.place_id);
              const failure = { locked: "lockedStop", catalog_limit: "catalogLimit", no_candidate: "noCandidate" };
              return (
                <article key={index} className="chat-bubble planner-suggestion">
                  {result.demo && <small>{plannerCopy.demoSuggestion}</small>}
                  {result.place ? (
                    <>
                      <dl>
                        <div><dt>{plannerCopy.before}</dt><dd>{original?.names[language] ?? original?.names.en ?? target.place_id}</dd></div>
                        <div><dt>{plannerCopy.after}</dt><dd>{result.place.names[language] ?? result.place.names.en}</dd></div>
                      </dl>
                      {result.reason && <p lang={message.lang}>{result.reason}</p>}
                      {message.applied ? <p>{plannerCopy.applied}</p> : snapshot === course ? (
                        <button type="button" disabled={Boolean(pending)} onClick={() => applySuggestion(message)}>{plannerCopy.apply}</button>
                      ) : <p>{plannerCopy.stale}</p>}
                    </>
                  ) : <p>{result.reason ? <span lang={message.lang}>{result.reason}</span> : plannerCopy[failure[result.reason_code]]}</p>}
                </article>
              );
            })}
            {pending === "edit" && <p role="status">{plannerCopy.editing}</p>}
            {reviewStatus && <p role={reviewStatus === "applied" ? "status" : "alert"}>{plannerCopy[reviewStatus]}</p>}
          </div>

          {!showChat && (showPreferences ? (
            <TravelPreferences value={preferences} onChange={updatePreferences} onSubmit={recommendCourse} copy={plannerCopy} onShowRegions={showRegions}
              busy={Boolean(pending)} error={plannerCopy[planError]} backLabel={copy.itinerary} onBack={() => setShowPreferences(false)} />
          ) : (
            <section className="travel-panel" aria-label={copy.itinerary}>
              {course?.demo && <small>{plannerCopy.demoCourse}</small>}
              {plan.date && <time dateTime={plan.date}>{formatDate(plan.date, language)}</time>}
              {stops.length ? <PlanList plan={plan} places={places} displayLanguage={language}
                selected={selected} onSelect={selectStop} lockedLabel={copy.locked} onEdit={openEdit} editLabel={plannerCopy.editStop}
                formatStopDate={(date) => formatDate(date, language)} /> : <EmptyState message={copy.empty} />}
              {course?.lodging_unavailable && <p>{plannerCopy.lodgingUnavailable}</p>}
              {course?.limited_places && <p>{plannerCopy.limitedPlaces}</p>}
              {course?.unmatched_activities?.length > 0 && (
                <div className="activity-unmatched" role="status">
                  <p>{plannerCopy.activityCopy.unmatched}</p>
                  <ul>{course.unmatched_activities.map((activity) => <li key={activity}>{activity}</li>)}</ul>
                </div>
              )}
              {stops.length > 1 && <small>{plannerCopy.schematicRoute}</small>}
            </section>
          ))}
        </div>
        {showChat && editStop && (
          <div className="edit-target">
            <strong>{editIndex + 1} · {resolvePlaceName(editStop, placesById, language).name}</strong>
            <button type="button" aria-label={plannerCopy.clearTarget} onClick={() => { setEditId(null); setReviewStatus(null); }}>×</button>
          </div>
        )}
        <form className="chat-compose" hidden={!showChat} onSubmit={submit}>
          <textarea ref={composer} aria-label={copy.messageLabel} placeholder={copy.placeholder} rows={1}
            value={draft} maxLength={1000} onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
            }} />
          <button type="submit" aria-label={copy.send} disabled={!draft.trim() || !editStop || Boolean(pending)}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6" /></svg>
          </button>
        </form>
        {!showChat && !showPreferences && (
          <div className="trip-actions">
            {stops.length > 0 && (
              <button type="button" disabled={Boolean(pending)} onClick={() => changeTrip(!tripStarted)}>
                {tripStarted ? copy.endTrip : copy.startTrip}
              </button>
            )}
            <button type="button" disabled={Boolean(pending)} onClick={() => setShowPreferences(true)}>
              {stops.length ? plannerCopy.newCourse : plannerCopy.recommend}
            </button>
          </div>
        )}
      </aside>
      <nav ref={tabBar} className="travel-tabs" data-active-tab={tab} aria-label={copy.navigation} inert={regionDraft !== null}>
        <span className="travel-tab-indicator" aria-hidden="true" />
        {Object.entries(tabIcons).map(([name, path]) => (
          <button key={name} data-tab={name}
            type="button" aria-label={labels[name]} title={labels[name]}
            aria-current={tab === name ? "page" : undefined}
            aria-controls={name === "chat" || name === "itinerary" ? "travel-chat" : undefined}
            aria-expanded={name === "chat" || name === "itinerary" ? tab === name : undefined}
            onClick={() => {
              if (name !== "home") setEvent(null);
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
