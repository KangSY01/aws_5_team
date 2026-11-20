import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import TravelerProfileForm, { dietLabels, travelerCopy } from "./TravelerProfile.jsx";
import { ChatSources, CrowdLegend, RainNotice } from "../features/data-notices";
import { getSelectModeCopy } from "../constants/selectModeCopy.js";
import { getTravelCopy, languages } from "../constants/travelCopy.js";
import { closeLandmark, mapLandmarks } from "../constants/mapLandmarks.js";
import { getPlannerCopy, transportPreferenceIds, durationIds, areaIds } from "../constants/plannerCopy.js";
import { checkTravelPlan, delayTravelPlan, fetchPlan, hasConfiguredPlanApi, PlanClientError, saveTravelPlan, sendTravelMessage } from "../api/planClient.js";
import { translateText } from "../api/translationClient.js";
import { findStopAddition, recommendDemo, suggestDemo } from "../lib/demoPlanner.js";
import { activityTextKey, normalizeActivities } from "../lib/activityPreferences.js";
import { getTripStop, insertStopAfter, insertUnselectedStop, suggestLaterStop } from "../lib/itineraryTiming.js";
import { localeFlags } from "../constants/localeFlags.js";
import EmptyState from "./EmptyState.jsx";
import { mapEventName } from "../api/eventsClient.js";
import { useMapEvents } from "../hooks/useMapEvents.js";
import { useChatVoice } from "../hooks/useChatVoice.js";
import { activitySearch, fetchActivities } from "../api/activitiesClient.js";
import { formatTime } from "../lib/formatTime.js";
import catalogPlaces from "../mocks/places.json";
import regionalPlaces from "../mocks/regionalPlaces.json";
import { buildPlacesById, resolvePlaceName } from "../lib/resolvePlaceName.js";
import BusanMap from "./BusanMap.jsx";
import TranslationPage, { PhotoActionIcon, MicIcon, TextActionIcon } from "./TranslationPage.jsx";
import { getTranslationCopy } from "../constants/translationCopy.js";
import EmergencyHelp from "./EmergencyHelp.jsx";
import "./emergency-help.css";
import PlanList from "./PlanList.jsx";
import ChatPlaceCards from "./ChatPlaceCards.jsx";
import GuardianAlternatives from "./GuardianAlternatives.jsx";
import TravelActionDialog from "./TravelActionDialog.jsx";
import DelayForm from "./DelayForm.jsx";
import { LocalCardPicker } from "../features/local-card";
import { copyFor as localCardCopyFor } from "../features/local-card/phrases.js";
import { SCENES, useDemoSwitch } from "../features/demo-panel";
import { demoItineraryPrompt, makeLocalDemoCourse } from "../features/demo-panel/demoCourse.js";
import TravelPreferences from "./TravelPreferences.jsx";
import TripAlbum from "../features/trip-poster/TripAlbum.jsx";
import { saveCompletedTrip } from "../features/trip-poster/album.js";
import "./travel-preview.css";

// 디자인 실험(design/giljabi-ui): 넓은 화면에서는 왼쪽 사이드바 패널을 항상 연다.
// jsdom 처럼 matchMedia 가 없으면 false 라 기존 동작과 같다.
// 임시 로고 (디자인 실험). public/brand/ 의 SVG
const brandLogo = import.meta.env.BASE_URL + "brand/busannow-logo.svg";
const brandSymbol = import.meta.env.BASE_URL + "brand/busannow-symbol.svg";

const WIDE_QUERY = "(min-width: 900px)";
// 모바일 검색 알약 문구 (레퍼런스 "Search or ask Giljabi" 방식, 이름은 BusanNow)
const ASK_COPY = {
  ko: "BusanNow에게 물어보세요",
  en: "Search or ask BusanNow",
  ja: "BusanNowに聞いてみる",
  "zh-Hans": "向 BusanNow 提问",
  "zh-Hant": "向 BusanNow 提問",
};
// 데스크톱 사이드바 접기·펼치기 버튼 이름
const SIDEBAR_TOGGLE_COPY = {
  ko: ["패널 접기", "패널 펼치기"],
  en: ["Collapse panel", "Expand panel"],
  ja: ["パネルを閉じる", "パネルを開く"],
  "zh-Hans": ["收起面板", "展开面板"],
  "zh-Hant": ["收起面板", "展開面板"],
};
function useWideScreen() {
  const [wide, setWide] = useState(() => Boolean(globalThis.matchMedia?.(WIDE_QUERY).matches));
  useEffect(() => {
    const media = globalThis.matchMedia?.(WIDE_QUERY);
    if (!media) return undefined;
    const update = () => setWide(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  return wide;
}

const recommendationCatalog = buildPlacesById([...catalogPlaces, ...regionalPlaces]);

function chatRecommendations(answer, sources, placesById, language) {
  const candidates = new Map();
  for (const source of Array.isArray(sources) ? sources : []) {
    if (!["search_places", "get_place_info"].includes(source?.tool) || !source.id || !source.title) continue;
    const place = placesById.get(source.id) ?? recommendationCatalog.get(source.id) ??
      { place_id: source.id, names: { en: source.title } };
    candidates.set(source.id, { place, sourceTitle: source.title });
  }

  const nameKey = (name) => activityTextKey(name).replace(/\s/g, "").replace(/해수욕장$/, "해변");
  const remaining = [];
  for (const line of answer.replace(/[ \t]+(?=[-•]\s+\*\*)/g, "\n").split(/\r?\n/)) {
    const bullet = line.match(/^\s*(?:[-•*]|\d+[.)])\s+\*\*([^*]+)\*\*(.*)$/) ??
      line.match(/^\s*(?:[-•*]|\d+[.)])\s+([^:–—]+)[:–—]\s*(.*)$/);
    if (!bullet) {
      remaining.push(line);
      continue;
    }
    const heading = nameKey(bullet[1]);
    const option = [...candidates.values()].find(({ place, sourceTitle }) => {
      const names = [sourceTitle, ...Object.values(place.names), resolvePlaceName(place,
        new Map([[place.place_id, place]]), language).name];
      return names.some((name) => nameKey(name) === heading);
    });
    const detail = bullet[2].replace(/^\s*[:–—-]?\s*/, "").trim();
    if (!option || !detail || option.reason) {
      remaining.push(line);
      continue;
    }
    const sentenceEnd = detail.search(/[.!?。！？](?=\s)/u);
    option.reason = sentenceEnd < 0 ? detail : detail.slice(0, sentenceEnd + 1);
    if (sentenceEnd >= 0) remaining.push(detail.slice(sentenceEnd + 1).trim());
  }
  return { options: [...candidates.values()], text: remaining.join("\n").replace(/\*\*([^*]+)\*\*/g, "$1").trim() };
}

function issueAlternative(result, plan, demo, issue, target) {
  return { plan, demo, issue, target, repairs: result.repairs[issue.issue_id] ?? [], places: result.places };
}

function readTravelRoute() {
  const page = window.location.hash.slice(1);
  return page === "profile" ? page : "map";
}



const translationModes = ["text", "photo", "voice"];

const tabIcons = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z",
  itinerary: "M7 3v4m10-4v4M4 9h16M5 5h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1zm3 8h3m2 0h3m-8 4h3",
  chat: "M20 11.5a8 8 0 0 1-8 8 9 9 0 0 1-3.4-.7L4 20l1.2-4A8 8 0 1 1 20 11.5zM8.5 11.5h7",
  translation: "M3 5h12M9 3v2m4 0c-1 5-4 8-9 10m2-7c1 3 3 5 6 7m2 5 4-10 4 10m-7-3h6",
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

function loadPreferences(storageKey) {
  const { food, origin, ...saved } = loadSaved(storageKey) ?? {};
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

export function getSavedLanguage() {
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

function ProfilePage({ copy, language, onLanguageChange, demoMode, albumRevision, archiveError, traveler, onTravelerSave }) {
  const [languageOpen, setLanguageOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const labels = travelerCopy(language);
  const { name, age, gender, country, photo } = traveler;
  const ageLabel = age ? new Intl.NumberFormat(language, { style: "unit", unit: "year", unitDisplay: "long" }).format(Number(age)) : "";
  const dietNames = dietLabels(language);
  const diet = (Array.isArray(traveler.diet) ? traveler.diet : []).map((value) => dietNames[value]).filter(Boolean);
  const details = [ageLabel, gender && labels.genderNames[gender], country, ...diet].filter(Boolean);
  const heading = useRef(null);
  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, []);

  return (
    <section id="travel-profile" className="travel-profile" aria-labelledby="profile-heading">
      <div className="profile-content">
        <header>
          <h1 id="profile-heading" ref={heading} tabIndex={-1}>{copy.profile}</h1>
          <div className="profile-person">
            {photo && <img className="traveler-avatar" src={photo} alt="" width="68" height="68" />}
            <div className="traveler-profile-summary">
              {(name || details.length > 0) && <div className="traveler-profile-details">
                {name && <strong>{name}</strong>}
                {details.length > 0 && <p>{details.join(" · ")}</p>}
              </div>}
              <button type="button" className="traveler-profile-edit" onClick={() => setEditing(true)}>
                <span>
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="m15 5 4 4M4 20l4-.8L20 7l-3-3L5 16Z" />
                  </svg>
                  {labels.edit}
                </span>
              </button>
            </div>
          </div>
        </header>
        <TripAlbum language={language} demoMode={demoMode} revision={albumRevision} archiveError={archiveError}
          formatDate={(date) => formatDate(date, language)} />
        <section className="profile-settings" aria-labelledby="profile-settings-title">
          <h2 id="profile-settings-title">{copy.settings}</h2>
          <button type="button" className="profile-language-row" aria-expanded={languageOpen}
            aria-controls="profile-languages" onClick={() => setLanguageOpen(!languageOpen)}>
            <span>{copy.languageLabel}</span>
            <span className="profile-language-value" lang={language}>{languages[language]}</span>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="m9 6 6 6-6 6" />
            </svg>
          </button>
          <div id="profile-languages" className="profile-language-options" hidden={!languageOpen}
            role="group" aria-label={copy.languageLabel}>
            <LanguageOptions language={language} onSelect={onLanguageChange} />
          </div>
        </section>
      </div>
      {editing && <TravelActionDialog title={labels.edit}
        onClose={() => setEditing(false)} className="traveler-profile-dialog">
        <TravelerProfileForm language={language} initial={traveler} onCancel={() => setEditing(false)}
          onSave={(profile) => { onTravelerSave(profile); setEditing(false); }} />
      </TravelActionDialog>}
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

export default function TravelPreview({ night = false, demoMode = false, traveler = {}, onTravelerSave } = {}) {
  // 여행자 프로필의 식사 제한. 모든 채팅·추천 요청의 profile.diet 로 보낸다
  const travelerDiet = Array.isArray(traveler?.diet) ? traveler.diet : [];
  const suffix = demoMode ? ".demo" : "";
  const courseKey = courseStorageKey + suffix;
  const activeTripKey = activeTripStorageKey + suffix;
  const preferencesKey = preferencesStorageKey + suffix;
  const [language, setLanguage] = useState(getSavedLanguage);
  const [route, setRoute] = useState(readTravelRoute);
  const [translationMenu, setTranslationMenu] = useState(false);
  const [translationMode, setTranslationMode] = useState(null);
  const [translationExpanded, setTranslationExpanded] = useState(false);
  const page = route;
  const [open, setOpen] = useState(false);
  const wide = useWideScreen();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [course, setCourse] = useState(() => {
    const saved = loadSaved(courseKey);
    return Array.isArray(saved?.plan?.stops) && Array.isArray(saved?.places) ? saved : null;
  });
  const [tripStarted, setTripStarted] = useState(() => {
    try {
      return Boolean(course && window.localStorage.getItem(activeTripKey) === course.plan.plan_id);
    } catch {
      return false;
    }
  });
  const [tripTime, setTripTime] = useState(Date.now);
  const [albumRevision, setAlbumRevision] = useState(0);
  const [archiveError, setArchiveError] = useState(false);
  const [preferences, setPreferences] = useState(() => loadPreferences(preferencesKey));
  const [showPreferences, setShowPreferences] = useState(false);
  const [selectedMapDetail, setMapDetail] = useState(null);
  const [regionDraft, setRegionDraft] = useState(null);
  const regionSession = useRef(null);
  const restorePreferencesScroll = useRef(null);
  const [editId, setEditId] = useState(null);
  // 일정 선택 모드: 여러 장소를 골라 삭제하거나 AI 채팅에 멘션한다
  const [selectMode, setSelectMode] = useState(false);
  const [checkedIds, setCheckedIds] = useState([]);
  const [mentionIds, setMentionIds] = useState([]);
  const [reviewStatus, setReviewStatus] = useState(null);
  const [planError, setPlanError] = useState(null);
  const [pending, setPending] = useState(null);
  const requestInProgress = useRef(false);
  const generalChatSession = useRef(null);
  const [panel, setPanel] = useState("chat");
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState([]);
  const [guardian, setGuardian] = useState(null);
  const [guardianRefresh, setGuardianRefresh] = useState(0);
  const manualGuardianCheck = useRef(null);
  const [guardianLoading, setGuardianLoading] = useState(false);
  const [guardianActionError, setGuardianActionError] = useState(false);
  const [alternative, setAlternative] = useState(null);
  const [undoRepair, setUndoRepair] = useState(null);
  const [showReset, setShowReset] = useState(false);
  const [showDelay, setShowDelay] = useState(false);
  const [showLocalCard, setShowLocalCard] = useState(false);
  const demo = useDemoSwitch();
  const [scheduleSaveFailed, setScheduleSaveFailed] = useState(false);
  const liveApi = hasConfiguredPlanApi();
  const [selectedId, setSelectedId] = useState(() => course?.plan.stops[0]?.stop_id ?? null);
  const [mapFocus, setMapFocus] = useState(null);
  const dragStart = useRef(null);
  const root = useRef(null);
  const tabBar = useRef(null);
  const translationTrigger = useRef(null);
  const translationPopover = useRef(null);
  const chatHeading = useRef(null);
  const log = useRef(null);
  const composer = useRef(null);
  const languageMenu = useRef(null);
  const copy = getTravelCopy(language);
  const localCardCopy = localCardCopyFor(language);
  const plannerCopy = getPlannerCopy(language);
  const languageLabel = copy.languageLabel + ": " + languages[language];
  const plan = course?.plan ?? emptyPlan;
  const liveCourse = liveApi && Boolean(course?.session_id);
  const showDemoCourse = liveApi && demo.enabled && demo.now === SCENES[0].now;
  const places = course?.places ?? emptyPlaces;
  const placesById = useMemo(() => buildPlacesById(places), [places]);
  const stops = plan.stops;
  const rainIssue = guardian?.plan === plan && guardian.demo === demo
    ? guardian.issues?.find((issue) => issue.type === "rain" && guardian.repairs[issue.issue_id]?.length)
    : null;
  const rainStop = rainIssue && stops.find((stop) => stop.stop_id === rainIssue.stop_id);
  const demoTime = demoMode ? Date.parse(demo.now ?? SCENES[0].now) : NaN;
  const events = useMapEvents(liveApi, demoTime, placesById);
  const mapDetail = selectedMapDetail?.contentid
    ? events.find((event) => event.contentid === selectedMapDetail.contentid)
    : selectedMapDetail;
  const mapDetailName = mapDetail && mapEventName(mapDetail, language);
  const eventHours = mapDetail?.contentid && [formatTime(mapDetail.start), formatTime(mapDetail.end)];
  const travelTime = Number.isFinite(demoTime) ? demoTime : tripTime;
  const nextStop = tripStarted ? getTripStop(stops, travelTime) : null;
  const currentPlace = nextStop && Date.parse(nextStop.start) <= travelTime
    ? resolvePlaceName(nextStop, placesById, language).name : null;
  const editIndex = stops.findIndex((stop) => stop.stop_id === editId);
  const editStop = stops[editIndex];
  const selectCopy = getSelectModeCopy(language);
  const checkedStops = stops.filter((stop) => checkedIds.includes(stop.stop_id));
  const mentionStops = stops.filter((stop) => mentionIds.includes(stop.stop_id));
  const chipStops = editStop ? [editStop] : mentionStops; // 채팅 입력창 위에 @장소 칩으로 표시
  const selected = Math.max(0, stops.findIndex((stop) => stop.stop_id === selectedId));
  const profile = page === "profile";
  const isMap = page === "map";
  const translationCopy = getTranslationCopy(language);
  // 넓은 화면은 프로필 화면에서도 사이드바를 유지한다(하단 탭 위치가 바뀌지 않게). 지도 상세 카드는 홈 탭이 아니어도 보인다
  const sidebar = wide && !sidebarCollapsed;
  const sidebarMap = sidebar && isMap;
  const baseTab = isMap ? open || sidebarMap ? panel : "home" : page;
  const showTranslation = translationMode !== null;
  const sheetOpen = open || showTranslation || sidebar;
  const sheetExpanded = showTranslation ? translationExpanded : expanded;
  const tab = showTranslation || translationMenu ? "translation" : baseTab;
  const showChat = panel === "chat";
  const collapseLabel = showChat ? copy.collapse : copy.collapseItinerary;
  const closeLabel = showChat ? copy.close : copy.closeItinerary;
  const labels = { home: copy.home, itinerary: copy.itinerary, chat: copy.chat, translation: translationCopy.title, profile: copy.profile };

  const voiceAvailable = liveApi && language !== "ko";
  const voice = useChatVoice(voiceAvailable && sheetOpen && showChat && !showTranslation, language, setDraft);

  const initialDemoCourse = useRef({ course, tripStarted });

  useEffect(() => {
    const { course: cached, tripStarted: active } = initialDemoCourse.current;
    if (!demoMode || (cached && (!liveApi || active || !cached.plan.stops.length))) return;
    const request = new AbortController();
    requestInProgress.current = true;
    setPending("recommend");
    async function initializeDemo() {
      let next;
      try {
        if (liveApi) {
          const chat = await sendTravelMessage(demoItineraryPrompt, "ja", null, {}, request.signal);
          const saved = await fetchPlan(chat.plan_id, { signal: request.signal });
          if (saved.plan.stops.length) next = { ...saved, session_id: chat.session_id };
        }
      } catch {
        if (request.signal.aborted) return;
      }
      if (request.signal.aborted) return;
      next = { ...(next ?? cached ?? makeLocalDemoCourse()), preferences: cached?.preferences ?? defaultPreferences };
      setCourse(next);
      save(courseKey, next);
      setSelectedId(next.plan.stops[0].stop_id);
      requestInProgress.current = false;
      setPending(null);
    }
    void initializeDemo();
    return () => request.abort();
  }, [demoMode, liveApi, courseKey]);

  useEffect(() => {
    setAlternative(null);
    setGuardian(null);
    if (!liveCourse) {
      setGuardianLoading(false);
      return;
    }
    const request = new AbortController();
    setGuardianLoading(true);
    checkTravelPlan(plan.plan_id, request.signal).then((result) => {
      if (request.signal.aborted) return;
      const manual = manualGuardianCheck.current?.plan === plan && manualGuardianCheck.current.demo === demo;
      manualGuardianCheck.current = null;
      setGuardian({ ...result, plan, demo, manual });
      if (manual && result.issues.length === 1) {
        const [issue] = result.issues;
        const target = plan.stops.find((stop) => stop.stop_id === issue.stop_id);
        setAlternative(issueAlternative(result, plan, demo, issue, target));
      }
    }).catch(() => {
      if (request.signal.aborted) return;
      manualGuardianCheck.current = null;
      setGuardian({ error: true, plan });
    }).finally(() => {
      if (!request.signal.aborted) setGuardianLoading(false);
    });
    return () => request.abort();
  }, [liveCourse, plan, demo, guardianRefresh]);

  useEffect(() => {
    if (!tripStarted || Number.isFinite(demoTime)) return;
    let timer;
    function syncClock() {
      clearTimeout(timer);
      const now = Date.now();
      setTripTime(now);
      let delay = 30_000;
      for (const stop of stops) {
        for (const time of [stop.start, stop.end]) {
          const remaining = Date.parse(time) - now;
          if (remaining > 0) delay = Math.min(delay, remaining);
        }
      }
      timer = setTimeout(syncClock, delay);
    }
    syncClock();
    document.addEventListener("visibilitychange", syncClock);
    window.addEventListener("focus", syncClock);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", syncClock);
      window.removeEventListener("focus", syncClock);
    };
  }, [tripStarted, stops, demoTime]);

  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) return;
    const update = () => root.current?.style.setProperty("--visible-height", viewport.height + "px");
    update();
    viewport.addEventListener("resize", update);
    return () => viewport.removeEventListener("resize", update);
  }, []);

  useEffect(() => {
    if (open && baseTab === "chat" && log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [open, messages, baseTab, pending, reviewStatus]);

  useEffect(() => {
    if (baseTab === "itinerary" && log.current) {
      log.current.scrollTop = restorePreferencesScroll.current ?? 0;
      restorePreferencesScroll.current = null;
    }
  }, [baseTab, showPreferences]);

  useEffect(() => {
    if (sheetOpen) chatHeading.current?.focus({ preventScroll: true });
  }, [sheetOpen, tab]);

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
      const next = readTravelRoute();
      if (!window.history.state?.busanRegionPicker) exitRegionPicker(next === "map");
      setRoute(next);
      setTranslationMenu(false);
      setTranslationMode(null);
      if (next !== "map") {
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
    setMapDetail(null);
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

  function navigatePage(next) {
    if (route === next) return;
    const { pathname, search } = window.location;
    window.history.pushState(null, "", pathname + search + (next === "map" ? "" : "#" + next));
    setRoute(next);
  }

  useEffect(() => {
    if (!translationMenu) return;
    translationPopover.current?.querySelector("button")?.focus({ preventScroll: true });
    function dismissOutside(event) {
      if (!translationTrigger.current?.contains(event.target) && !translationPopover.current?.contains(event.target)) {
        setTranslationMenu(false);
      }
    }
    function dismissOnEscape(event) {
      if (event.key !== "Escape") return;
      event.stopPropagation();
      setTranslationMenu(false);
      translationTrigger.current?.focus({ preventScroll: true });
    }
    document.addEventListener("pointerdown", dismissOutside);
    document.addEventListener("keydown", dismissOnEscape, true);
    return () => {
      document.removeEventListener("pointerdown", dismissOutside);
      document.removeEventListener("keydown", dismissOnEscape, true);
    };
  }, [translationMenu]);

  function openTranslation(mode) {
    setTranslationMenu(false);
    if (!showTranslation) setTranslationExpanded(false);
    setTranslationMode(mode);
    if (translationMode === mode) chatHeading.current?.focus({ preventScroll: true });
  }

  function setSheetExpanded(next) {
    if (showTranslation) setTranslationExpanded(next);
    else setExpanded(next);
  }


  function close() {
    if (showTranslation) {
      setTranslationMode(null);
      tabBar.current?.querySelector(`[data-tab="${baseTab}"]`)?.focus({ preventScroll: true });
      return;
    }
    setOpen(false);
    setExpanded(false);
    tabBar.current?.querySelector(`[data-tab="${panel}"]`)?.focus();
  }

  function resetItinerary() {
    if (tripStarted || !stops.length || requestInProgress.current) return;
    // A saved empty demo course prevents automatic demo seeding after a reset.
    const cleared = demoMode ? { plan: emptyPlan, places: emptyPlaces } : null;
    if (demoMode) save(courseKey, cleared);
    else {
      try {
        window.localStorage.removeItem(courseKey);
      } catch {
        // The current session can still be cleared when storage is unavailable.
      }
    }
    changeTrip(false, false);
    setCourse(cleared);
    setSelectedId(null);
    setMapFocus(null);
    setEditId(null);
    setDraft("");
    setMessages((previous) => previous.filter((message) => !message.result && !message.options));
    generalChatSession.current = null;
    setReviewStatus(null);
    setPlanError(null);
    setScheduleSaveFailed(false);
    setGuardian(null);
    setGuardianActionError(false);
    setAlternative(null);
    setUndoRepair(null);
    setShowReset(false);
    requestAnimationFrame(() => chatHeading.current?.focus());
  }

  function changeTrip(active, closePanel = true) {
    if (active && !stops.length) return;
    setTripStarted(active);
    try {
      if (active) window.localStorage.setItem(activeTripKey, plan.plan_id);
      else window.localStorage.removeItem(activeTripKey);
    } catch {
      // Travel mode remains available in the current session without storage.
    }
    if (closePanel) {
      setOpen(false);
      setExpanded(false);
      tabBar.current?.querySelector('[data-tab="home"]')?.focus();
    }
    if (active) {
      const now = Number.isFinite(demoTime) ? demoTime : Date.now();
      const target = getTripStop(stops, now);
      setTripTime(now);
      if (target) {
        setSelectedId(target.stop_id);
        setMapFocus({ id: target.stop_id });
      }
    }
  }

  function toggleTrip() {
    if (tripStarted && course?.plan.stops.length) {
      void saveCompletedTrip(course, demoMode).then(() => {
        setArchiveError(false);
        setAlbumRevision((revision) => revision + 1);
      }).catch(() => setArchiveError(true));
    }
    changeTrip(!tripStarted);
  }

  function selectStop(index) {
    const id = stops[index].stop_id;
    setSelectedId(id);
    setMapFocus({ id });
  }

  function updatePreferences(next) {
    setPreferences(next);
    save(preferencesKey, next);
  }

  async function recommendCourse(event, runDemo = demoMode) {
    event.preventDefault();
    if (requestInProgress.current) return;
    const { foodTags, customFoods, ...answers } = preferences;
    const values = { ...answers, activities: normalizeActivities(preferences.activities), food: [...foodTags, ...customFoods].join(", "),
      lodging: ["overnight", "long"].includes(preferences.duration) && preferences.lodging };
    requestInProgress.current = true;
    setPending("recommend");
    setPlanError(null);
    let stage = "generation";
    try {
      let result;
      if (liveApi) {
        const english = getPlannerCopy("en");
        const interests = values.activities.map((id) => english.activityCopy.keywords[id] ?? id).concat(values.customActivities);
        const message = [
          "Create and save a new Busan travel itinerary for today in Busan.",
          "Duration (required): " + english.durations[durationIds.indexOf(values.duration)],
          "Area, activity, cuisine, transport, and lodging preferences below are ranking hints.",
          "Plan around mealtimes even when no cuisine is selected. Set aside 45–60 minutes for lunch when the itinerary spans midday, and for dinner if it spans the evening meal.",
          "Prefer a verified food market or another catalog location where visitors can eat as a meal stop. If no verified food venue fits, leave an actual meal break between stops rather than filling that time with sightseeing. Never invent venues.",
          "If the catalog has no match for an area, activity, or food preference, skip that preference and use nearby verified alternatives.",
          "Use one broad catalog search to gather candidates. As soon as you have enough candidates, call the itinerary-building tool before making extra lookups.",
          "Save a valid itinerary even if only some preferences can be met. Do not ask for a date or a new request if a valid itinerary can be built.",
          values.regions.length && "Areas: " + values.regions.map((id) => english.areasList[areaIds.indexOf(id)] ?? id).join(", "),
          interests.length && "Activities: " + interests.join(", "),
          (foodTags.length || customFoods.length) && "Food preferences: " + [...foodTags.map((id) => english.foodLabels[id] ?? id), ...customFoods].join(", "),
          values.transport && "Transport: " + (english.transportLabels[values.transport] ?? values.transport),
          values.less_walking && "Prefer shorter walks.",
          values.lodging && "Include lodging suggestions when available.",
          traveler.notes && "Respect these traveler notes when recommending places and building the itinerary: " + traveler.notes,
        ].filter(Boolean).join("\n");
        const chat = runDemo
          ? await sendTravelMessage(demoItineraryPrompt, "ja", null)
          : await sendTravelMessage(message, language, null, { interests, diet: travelerDiet });
        stage = "lookup";
        const saved = await fetchPlan(chat.plan_id);
        if (!saved.plan.stops.length) {
          setPlanError(plannerCopy.emptyRecommendation);
          return;
        }
        result = { ...saved, session_id: chat.session_id };
      } else {
        result = runDemo ? makeLocalDemoCourse() : await recommendDemo(values, language, traveler.notes);
      }
      if (!result?.plan?.plan_id || !result.plan.stops?.length || !Array.isArray(result.places)) throw new Error();
      const next = { ...result, preferences: values };
      setCourse(next);
      save(courseKey, next);
      if (tripStarted) changeTrip(false, false);
      setSelectedId(result.plan.stops[0].stop_id);
      setMapFocus(null);
      setEditId(null);
      setGuardian(null);
      setShowPreferences(false);
      if (runDemo) {
        setDraft("");
        setPanel("itinerary");
        setOpen(true);
      }
    } catch (error) {
      if (error instanceof PlanClientError) {
        const title = copy.errorTitles[error.kind] ?? plannerCopy.requestFailed;
        const diagnostic = [
          stage === "generation" ? "POST /chat" : "GET /plan",
          error.status && "HTTP " + error.status,
          error.requestId && "AWS ID " + error.requestId,
        ].filter(Boolean).join(" · ");
        const message = error.status >= 500 ? plannerCopy.planServerError[stage] : title;
        setPlanError(message + " (" + diagnostic + ")");
      } else {
        setPlanError(error.message === "noPlaces" ? plannerCopy.noPlaces : plannerCopy.requestFailed);
      }
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

  function proposeStop(place, anchorIndex, startMinutes, duration) {
    const result = anchorIndex >= 0
      ? insertStopAfter(stops, anchorIndex, place.place_id, startMinutes, undefined, duration)
      : insertUnselectedStop(plan, place.place_id, startMinutes, duration);
    return result;
  }

  async function confirmChatPlace(message, place, start, duration) {
    if (requestInProgress.current || message.plan !== plan) return plannerCopy.stale;
    const inserted = proposeStop(place, message.anchorIndex, [start], duration);
    if (!inserted) return plannerCopy.additionNoTime;
    requestInProgress.current = true;
    setPending("edit");
    try {
      await persistEditedStops(inserted, place);
      setMessages((previous) => previous.map((entry) => entry === message ? { ...entry, confirmed: place.place_id } : entry));
      return null;
    } catch (error) {
      const details = error instanceof PlanClientError && error.status ? " (PUT /plan · HTTP " + error.status + ")" : "";
      return plannerCopy.requestFailed + details;
    } finally {
      requestInProgress.current = false;
      setPending(null);
    }
  }

  async function submit(event) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || voice.phase || editStop?.locked || requestInProgress.current) return;
    if (liveApi && !editStop && draft === demoItineraryPrompt) {
      await recommendCourse(event, true);
      return;
    }
    requestInProgress.current = true;
    setPending(editStop ? "edit" : "chat");
    setReviewStatus(null);
    const mentionText = chipStops.map((stop) => "@" + resolvePlaceName(stop, placesById, language).name).join(" ");
    setMessages((previous) => [...previous, { text: mentionText ? mentionText + " " + message : message, lang: language, role: "user" }]);
    setDraft("");
    let requestStage = "POST /chat";
    try {
      if (mentionStops.length && liveApi && course?.session_id) {
        // 선택 모드에서 멘션한 장소들. 바꾸라는 요청이면 이 장소들만 바꾸고 나머지는 지키도록 넘긴다
        const instruction = [
          "The traveler selected these stops in the current itinerary. If the request asks for a change, change only these stops, keep their stop IDs where possible, and preserve every other stop. If it is a question, answer about these stops.",
          ...mentionStops.map((stop) => "- " + stop.stop_id + " (" + resolvePlaceName(stop, placesById, language).name + ", "
            + formatTime(stop.start) + "–" + formatTime(stop.end) + (stop.locked ? ", locked" : "") + ")"),
          "Traveler request: " + message,
        ].join("\n");
        const chat = await sendTravelMessage(instruction, language, { session_id: course.session_id, plan_id: plan.plan_id }, { ...plan.profile, diet: travelerDiet });
        requestStage = "GET /plan";
        const result = await fetchPlan(chat.plan_id);
        const next = { ...course, ...result, session_id: chat.session_id };
        setCourse(next);
        save(courseKey, next);
        setGuardian(null);
        setMentionIds([]);
        let answer = chat.answer;
        if (chat.language !== language) {
          try {
            answer = await translateText(chat.answer, chat.language, language, AbortSignal.timeout(8000));
          } catch {
            answer = chat.plan_changes?.length ? plannerCopy.chatPlanUpdated : plannerCopy.chatPlanUnchanged;
          }
        }
        setMessages((previous) => [...previous, { text: answer, sources: chat.sources, lang: language, role: "assistant" }]);
        return;
      }
      const activity = !editStop && activitySearch(message);
      if (activity) {
        let options = [];
        let unavailable = !liveApi;
        if (liveApi) {
          const result = await fetchActivities(activity);
          ({ options, unavailable } = result);
        }
        setMessages((previous) => [...previous, options.length
          ? { options, readOnly: true, lang: language }
          : { role: "assistant", text: unavailable ? plannerCopy.placeCards.searchUnavailable : plannerCopy.placeCards.searchEmpty, lang: language }]);
        return;
      }
      const addition = findStopAddition(message, places);
      if (addition?.places.length) {
        const options = addition.places.map((place) => {
          const inserted = stops.length && proposeStop(place, editIndex, addition.startMinutes);
          const suggested = inserted
            ? inserted.find((stop) => !stops.includes(stop))
            : stops.length && suggestLaterStop(plan, place.place_id, addition.startMinutes, editIndex);
          return { place, suggested, match: addition.match, requestedUnavailable: Boolean(stops.length && !inserted && addition.startMinutes) };
        });
        setMessages((previous) => [...previous, { options, plan, anchorIndex: editIndex, readOnly: editIndex < 0 && !addition.adding }]);
        return;
      }
      if (addition) {
        setReviewStatus("limitedPlaces");
        return;
      }
      if (!editStop) {
        if (liveApi) {
          const chat = await sendTravelMessage(draft, language, generalChatSession.current, { diet: travelerDiet });
          generalChatSession.current = { session_id: chat.session_id, plan_id: chat.plan_id };
          let answer = chat.answer;
          let answerLanguage = chat.language ?? language;
          if (answerLanguage !== language) {
            try {
              answer = await translateText(answer, answerLanguage, language, AbortSignal.timeout(8000));
              answerLanguage = language;
            } catch {
              // Keep the reply available when translation fails.
            }
          }
          const { options, text } = chatRecommendations(answer, chat.sources, placesById, language);
          setMessages((previous) => [
            ...previous,
            { text, sources: chat.sources, lang: answerLanguage, role: "assistant" },
            ...(options.length ? [{ options, readOnly: true, lang: answerLanguage }] : []),
          ]);
        } else {
          const query = activityTextKey(message).replace(/\s/g, "");
          const landmark = mapLandmarks.find(({ names }) => Object.values(names)
            .some((name) => query.includes(activityTextKey(name).replace(/\s/g, ""))));
          setMessages((previous) => [...previous, {
            text: landmark?.description[language] ?? plannerCopy.generalChatDemo,
            lang: language, role: "assistant",
          }]);
        }
        return;
      }
      if (liveApi && course.session_id) {
        const instruction = [
          "Replace only this stop if possible. Keep its stop ID, start and end times, and preserve every other stop.",
          "Stop: " + editStop.stop_id + " (" + resolvePlaceName(editStop, placesById, language).name + ")",
          "Traveler request: " + message,
        ].join("\n");
        const chat = await sendTravelMessage(instruction, language, { session_id: course.session_id, plan_id: plan.plan_id }, { ...plan.profile, diet: travelerDiet });
        requestStage = "GET /plan";
        const result = await fetchPlan(chat.plan_id);
        const next = { ...course, ...result, session_id: chat.session_id };
        setCourse(next);
        save(courseKey, next);
        setGuardian(null);
        if (result.plan.stops.some((stop) => stop.stop_id === editId)) {
          setSelectedId(editId);
          setMapFocus({ id: editId });
        }
        let answer = chat.answer;
        if (chat.language !== language) {
          try {
            answer = await translateText(chat.answer, chat.language, language, AbortSignal.timeout(8000));
          } catch {
            const updatedStop = result.plan.stops.find((stop) => stop.stop_id === editId);
            const name = updatedStop && resolvePlaceName(updatedStop, buildPlacesById(result.places), language).name;
            answer = chat.plan_changes?.length
              ? name && updatedStop.place_id !== editStop.place_id
                ? plannerCopy.chatStopReplaced(name)
                : plannerCopy.chatPlanUpdated
              : plannerCopy.chatPlanUnchanged;
          }
        }
        setMessages((previous) => [...previous, { text: answer, sources: chat.sources, lang: language, role: "assistant" }]);
        return;
      }
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
    } catch (error) {
      setDraft((current) => current || message);
      if (error instanceof PlanClientError) {
        const diagnostic = [requestStage, error.status && "HTTP " + error.status, error.requestId && "AWS ID " + error.requestId]
          .filter(Boolean).join(" · ");
        setMessages((previous) => [...previous, {
          text: (copy.errorTitles[error.kind] ?? plannerCopy.requestFailed) + " (" + diagnostic + ")",
          lang: language, role: "assistant", error: true,
        }]);
      } else {
        setReviewStatus("requestFailed");
      }
    } finally {
      requestInProgress.current = false;
      setPending(null);
    }
  }

  async function guardianAction(action) {
    if (!liveCourse || requestInProgress.current) return;
    requestInProgress.current = true;
    setPending("guardian");
    setGuardianActionError(false);
    try {
      await action();
    } catch {
      setGuardianActionError(true);
    } finally {
      requestInProgress.current = false;
      setPending(null);
    }
  }

  function applyRepair(repair) {
    void guardianAction(async () => {
      if (alternative?.plan !== plan || alternative.demo !== demo) throw new Error("stale");
      const latest = await fetchPlan(plan.plan_id);
      if (latest.plan.stops.length !== stops.length || latest.plan.stops.some((stop, index) => {
        const previous = stops[index];
        return stop.stop_id !== previous.stop_id || stop.place_id !== previous.place_id ||
          stop.locked !== previous.locked || Date.parse(stop.start) !== Date.parse(previous.start) ||
          Date.parse(stop.end) !== Date.parse(previous.end);
      })) throw new Error("stale");
      const changes = new Map(repair.changes.map((change) => [change.stop_id, change]));
      if (stops.some((stop) => stop.locked && changes.has(stop.stop_id))) throw new Error("locked");
      const nextStops = stops.flatMap((stop) => changes.has(stop.stop_id) ? changes.get(stop.stop_id).after ?? [] : stop);
      const stopIds = new Set(stops.map((stop) => stop.stop_id));
      for (const { stop_id, before, after } of changes.values()) {
        if (!stopIds.has(stop_id)) {
          if (before || !after) throw new Error("stale");
          nextStops.push(after);
        }
      }
      nextStops.sort((left, right) => Date.parse(left.start) - Date.parse(right.start));
      const applied = await persistEditedStops(nextStops);
      setUndoRepair({ before: plan, applied });
      setAlternative(null);
    });
  }

  function toggleStopLock(stop) {
    void saveStops(stops.map((item) => item.stop_id === stop.stop_id
      ? { ...item, locked: !item.locked }
      : item));
  }

  function undoGuardianRepair() {
    void guardianAction(async () => {
      if (undoRepair?.applied !== plan) throw new Error("stale");
      await persistEditedStops(undoRepair.before.stops);
      setUndoRepair(null);
    });
  }

  function requestDelay(minutes) {
    void guardianAction(async () => {
      const result = await delayTravelPlan(plan.plan_id, minutes);
      setShowDelay(false);
      setAlternative({ plan, demo, repairs: result.repairs, places: result.places, kind: "delay" });
    });
  }

  function openDelay() {
    setGuardianActionError(false);
    setShowDelay(true);
  }

  function renderStopChecks(stop) {
    const issues = guardian?.plan === plan
      ? guardian.issues?.filter((issue) => issue.stop_id === stop.stop_id && issue.severity === "high")
      : null;
    const name = resolvePlaceName(stop, placesById, language).name;
    if (!issues?.length) return null;
    return (
      <div className="guardian-stop-controls">
        {issues?.map((issue) => {
          const label = issue.type === "crowded" ? copy.guardian.crowdingWarning : copy.guardian.warning;
          return (
            <button key={issue.issue_id} type="button" className="guardian-badge" data-crowding={issue.type === "crowded"}
              aria-label={label + " · " + name} aria-description={formatTime(stop.start) + " – " + formatTime(stop.end)} aria-haspopup="dialog" disabled={Boolean(pending)}
              onClick={() => {
                setGuardianActionError(false);
                setAlternative(issueAlternative(guardian, plan, demo, issue, stop));
              }}>
              <span className="guardian-dot" aria-hidden="true" />
              {label}
            </button>
          );
        })}
      </div>
    );
  }

  async function persistEditedStops(nextStops, addedPlace) {
    const nextPlan = { ...plan, stops: nextStops };
    const saved = liveApi && course.session_id ? await saveTravelPlan(nextPlan) : { plan: nextPlan };
    if (addedPlace && (saved.plan.stops.length !== nextStops.length ||
        !nextStops.every((stop, index) => saved.plan.stops[index]?.stop_id === stop.stop_id))) {
      throw new PlanClientError("invalid_response");
    }
    const nextPlaces = buildPlacesById([...places, ...(addedPlace ? [addedPlace] : []), ...(saved.places ?? [])]);
    const next = { ...course, ...saved, places: [...nextPlaces.values()] };
    setCourse(next);
    save(courseKey, next);
    setGuardian(null);
    return next.plan;
  }

  // 지도 핀: 선택 모드에서는 체크 전환, 평소에는 일정 칸 선택
  const selectPin = useCallback((id) => {
    if (!selectMode) return setSelectedId(id);
    setCheckedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }, [selectMode]);

  function toggleSelectMode() {
    setSelectMode((value) => !value);
    setCheckedIds([]);
  }

  function toggleChecked(index) {
    const id = stops[index]?.stop_id;
    if (!id) return;
    setCheckedIds((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  async function deleteChecked() {
    const removable = checkedStops.filter((stop) => !stop.locked).map((stop) => stop.stop_id);
    if (!removable.length) return;
    const ok = await saveStops(stops.filter((stop) => !removable.includes(stop.stop_id)));
    if (ok) {
      setCheckedIds([]);
      setMentionIds((current) => current.filter((id) => !removable.includes(id)));
    }
  }

  function mentionChecked() {
    if (!checkedStops.length) return;
    // 고정되지 않은 한 곳: 기존 단일 장소 수정 흐름(데모 응답, 제안 카드 적용) 사용. 여러 곳·고정 장소: 멘션 요청
    const single = checkedStops.length === 1 && !checkedStops[0].locked;
    setEditId(single ? checkedStops[0].stop_id : null);
    setMentionIds(single ? [] : checkedStops.map((stop) => stop.stop_id));
    setSelectMode(false);
    setCheckedIds([]);
    setReviewStatus(null);
    setPanel("chat");
    setOpen(true);
  }

  async function saveStops(nextStops) {
    if (requestInProgress.current) return false;
    requestInProgress.current = true;
    setPending("schedule");
    setScheduleSaveFailed(false);
    try {
      await persistEditedStops(nextStops);
      return true;
    } catch {
      setScheduleSaveFailed(true);
      return false;
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
    save(courseKey, next);
    setSelectedId(message.target.stop_id);
    setMapFocus({ id: message.target.stop_id });
    setMessages((previous) => previous.map((entry) => entry === message ? { ...entry, applied: true } : entry));
    setReviewStatus("applied");
  }

  function endDrag(event) {
    if (dragStart.current === null) return;
    const distance = event.clientY - dragStart.current;
    dragStart.current = null;
    if (distance < -35) setSheetExpanded(true);
    if (distance > 35) {
      if (sheetExpanded) setSheetExpanded(false);
      else close();
    }
  }

  // 지도 마커 혼잡도 (디자인 실험): Guardian 점검의 crowded 이슈. high=busy, medium=moderate, 없음·low=calm. 점검 전이면 null
  const crowdLevels = guardian?.plan === plan && Array.isArray(guardian.issues)
    ? Object.fromEntries(stops.map((stop) => {
      const issue = guardian.issues.find((item) => item.stop_id === stop.stop_id && item.type === "crowded");
      return [stop.stop_id, issue?.severity === "high" ? "busy" : issue?.severity === "medium" ? "moderate" : "calm"];
    }))
    : null;

  function openChat() {
    navigatePage("map");
    setShowPreferences(false);
    setPanel("chat");
    setOpen(true);
  }

  return (
    <main ref={root} className="travel-preview" data-trip-active={tripStarted} data-night={night} data-page={page} data-sheet={sheetOpen ? "open" : "closed"} data-expanded={sheetExpanded}
      data-compact-itinerary={!showTranslation && !showChat && !showPreferences && !stops.length} data-region-picker={regionDraft !== null} data-sidebar={sidebar} lang={language}>
      <div className="travel-shell" inert={!isMap} aria-hidden={!isMap}>
        <BusanMap plan={plan} places={places} events={events} onEventSelect={setMapDetail} onLandmarkSelect={setMapDetail}
          language={language} label={copy.map} locationCopy={copy.location}
          selectedId={selectedId} nextStopId={nextStop?.stop_id}
          onSelect={selectPin} focusRequest={mapFocus} crowdLevels={crowdLevels}
          regionPicker={regionDraft && {
            selected: regionDraft, onChange: setRegionDraft, copy: plannerCopy,
            onDone: () => finishRegions(true), onCancel: () => finishRegions(false),
          }} />
        {crowdLevels && stops.length > 0 && !regionDraft && <CrowdLegend language={language} />}
        <header className="travel-header">
          <button type="button" className="travel-ask" aria-controls="travel-chat" onClick={openChat}>
            <img className="travel-ask__mark" src={brandSymbol} alt="" aria-hidden="true" />
            <span className="travel-ask__text">{ASK_COPY[language] ?? ASK_COPY.en}</span>
          </button>
          <div className="travel-brand-column">
            <div className="travel-brand-group">
              <span className="travel-brand"><img className="travel-brand__logo" src={brandLogo} alt="BusanNow" /></span>
              {tripStarted && <span className="trip-status">{copy.traveling}</span>}
            </div>
            {(tab === "home" || sidebarMap) && !regionDraft && (currentPlace || mapDetail) && (
              <div className="travel-map-cards">
                {currentPlace && (
                  <div className="trip-next">
                    <span>{copy.currentPlace}</span>
                    <strong>{currentPlace}</strong>
                  </div>
                )}
                {mapDetail && (
                  <section id="busan-map-detail" className="map-event-card" data-landmark={Boolean(mapDetail.description)} aria-label={mapDetailName}>
                    <button type="button" aria-label={mapDetail.description ? closeLandmark[language] : plannerCopy.closeEvent} onClick={() => setMapDetail(null)}>×</button>
                    <h2>{mapDetailName}</h2>
                    {mapDetail.description ? <p>{mapDetail.description[language]}</p> : (
                      <>
                        <p>{formatDate(mapDetail.period_start.slice(0, 10), language)}{mapDetail.period_start.slice(0, 10) !== mapDetail.period_end.slice(0, 10) &&
                          " – " + formatDate(mapDetail.period_end.slice(0, 10), language)}</p>
                        {eventHours && !eventHours.includes("--:--") && eventHours.join() !== "00:00,23:59" && <p>{eventHours.join(" – ")}</p>}
                        {mapDetail.place && <p>{mapDetail.place.names[language] ?? mapDetail.place.names.ko ?? mapDetail.place.names.en}</p>}
                      </>
                    )}
                  </section>
                )}
              </div>
            )}
          </div>
          <div className="travel-map-tools">
            <EmergencyHelp copy={copy.emergency} />
            <button type="button" className="travel-phrases" aria-haspopup="dialog" onClick={() => setShowLocalCard(true)}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d={tabIcons.chat} />
              </svg>
              <span>{localCardCopy.trigger}</span>
            </button>
          </div>
          <LanguageTrigger className="travel-language-trigger" label={languageLabel} />
          {!regionDraft && <div className="travel-rain-notice">
            <RainNotice key={demo.weatherPreset} language={language}
              placeName={rainStop && resolvePlaceName(rainStop, placesById, language).name}
              disabled={guardianLoading || Boolean(pending)}
              onOpen={rainIssue ? () => {
                setGuardianActionError(false);
                setAlternative(issueAlternative(guardian, plan, demo, rainIssue, rainStop));
              } : undefined} />
          </div>}
          <div id="travel-language-menu" className="travel-language-menu" ref={languageMenu}
            popover="auto" role="group" aria-label={copy.languageLabel}>
            <LanguageOptions language={language} onSelect={(code) => {
              changeLanguage(code);
              languageMenu.current.hidePopover();
            }} />
          </div>
        </header>
      </div>
      {profile && <ProfilePage copy={copy} language={language} onLanguageChange={changeLanguage}
        demoMode={demoMode} albumRevision={albumRevision} archiveError={archiveError}
        traveler={traveler} onTravelerSave={onTravelerSave} />}
      {wide && isMap && (
        <button type="button" className="sidebar-toggle" aria-controls="travel-chat" aria-expanded={!sidebarCollapsed}
          aria-label={(SIDEBAR_TOGGLE_COPY[language] ?? SIDEBAR_TOGGLE_COPY.en)[sidebarCollapsed ? 1 : 0]}
          onClick={() => setSidebarCollapsed((value) => !value)}>
          <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d={sidebarCollapsed ? "m9 6 6 6-6 6" : "m15 6-6 6 6 6"} />
          </svg>
        </button>
      )}
      <aside id="travel-chat" className="travel-chat" data-translation={showTranslation} hidden={!sheetOpen} inert={!sheetOpen} aria-hidden={!sheetOpen} aria-labelledby="travel-panel-title"
        onKeyDown={(event) => { if (event.key === "Escape") close(); }}>
        {sidebar && <div className="sidebar-brand"><img className="travel-brand__logo" src={brandLogo} alt="BusanNow" /></div>}
        <div className="chat-grab" aria-hidden="true"
          onPointerDown={(event) => {
            dragStart.current = event.clientY;
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerUp={endDrag} onPointerCancel={() => { dragStart.current = null; }} />
        <header className="chat-heading">
          <h1 id="travel-panel-title" ref={chatHeading} tabIndex={-1}>{showTranslation ? translationCopy[translationMode] : showChat ? "Busan AI" : copy.itinerary}</h1>
          {showTranslation && <button type="button" aria-label={sheetExpanded ? copy.reduce : copy.expand}
            aria-expanded={sheetExpanded} onClick={() => setSheetExpanded(!sheetExpanded)}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d={sheetExpanded ? "m6 9 6 6 6-6" : "m6 15 6-6 6 6"} /></svg>
          </button>}
          {!showTranslation && !showChat && !showPreferences && liveCourse && tripStarted && stops.length > 0 && (
            <button type="button" className="itinerary-delay" aria-haspopup="dialog"
              disabled={Boolean(pending)} onClick={openDelay}>
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" />
              </svg>
              <span>{copy.guardian.late}</span>
            </button>
          )}
          {sheetOpen && !showTranslation && !showChat && !showPreferences && !tripStarted && stops.length > 0 && (
            <button type="button" className="itinerary-select-toggle" aria-pressed={selectMode}
              aria-label={selectMode ? selectCopy.done : selectCopy.toggle} title={selectMode ? selectCopy.done : selectCopy.toggle}
              disabled={Boolean(pending)} onClick={toggleSelectMode}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="3" /><path d="m8 12 3 3 5-6" /></svg>
            </button>
          )}
          {sheetOpen && !showTranslation && !showChat && !showPreferences && !tripStarted && stops.length > 0 && (
            <details className="itinerary-options"
              onBlur={(event) => {
                if (!event.currentTarget.contains(event.relatedTarget)) event.currentTarget.open = false;
              }}
              onKeyDown={(event) => {
                if (event.key !== "Escape" || !event.currentTarget.open) return;
                event.stopPropagation();
                event.currentTarget.open = false;
                event.currentTarget.querySelector("summary").focus();
              }}>
              <summary aria-label={copy.resetItinerary.menu}>⋯</summary>
              <div className="itinerary-options-popover">
                <button type="button" disabled={Boolean(pending)} aria-haspopup="dialog" onClick={(event) => {
                  const options = event.currentTarget.closest("details");
                  options.open = false;
                  options.querySelector("summary").focus();
                  setShowReset(true);
                }}>{copy.resetItinerary.action}</button>
              </div>
            </details>
          )}
          <button type="button" className="chat-collapse" aria-label={showTranslation ? translationCopy.close : collapseLabel} onClick={close}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
          </button>
          <button type="button" className="chat-close" aria-label={showTranslation ? translationCopy.close : closeLabel} onClick={close}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
          </button>
          {showTranslation && (
            <div className="activity-chips translation-mode-chips" role="group" aria-label={translationCopy.title}>
              {translationModes.map((mode) => (
                <button key={mode} type="button" className="activity-chip" aria-pressed={mode === translationMode}
                  onClick={() => setTranslationMode(mode)}>{translationCopy[mode]}</button>
              ))}
            </div>
          )}
        </header>
        {translationModes.map((mode) => (
          <TranslationPage key={mode} mode={mode} active={mode === translationMode}
            language={language} copy={translationCopy} onInputFocus={() => setTranslationExpanded(true)} />
        ))}
        <div className="chat-content" ref={log} hidden={showTranslation}>
          <div className="chat-messages" role="log" hidden={!showChat}>
            <p className="chat-bubble">{copy.greeting}</p>
            <div className="travel-tool-actions travel-phrases-desktop">
              <button type="button" aria-haspopup="dialog" onClick={() => setShowLocalCard(true)}>{localCardCopy.trigger}</button>
            </div>
            {draft.trim() === demoItineraryPrompt && planError && <p role="alert">{planError}</p>}
            {messages.map((message, index) => {
              if (message.options) return <ChatPlaceCards key={index} message={message} language={language}
                copy={plannerCopy.placeCards} busy={Boolean(pending)} currentPlan={plan} onConfirm={confirmChatPlace} />;
              if (!message.result) return <Fragment key={index}>
                {message.text && <p className="chat-bubble" role={message.error ? "alert" : undefined} data-role={message.role} lang={message.lang}>{message.text}</p>}
                <ChatSources sources={message.sources} language={language} />
              </Fragment>;
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
            {pending === "edit" && <p className="chat-pending" role="status">{plannerCopy.editing}</p>}
            {(pending === "chat" || pending === "recommend") && <p className="chat-course-status" role="status">{copy.loading}</p>}
            {reviewStatus && <p role={reviewStatus === "applied" ? "status" : "alert"}>{plannerCopy[reviewStatus]}</p>}
          </div>

          {!showChat && (showPreferences ? (
            <TravelPreferences value={preferences} onChange={updatePreferences} onSubmit={recommendCourse} copy={plannerCopy} onShowRegions={showRegions}
              busy={Boolean(pending)} error={planError} backLabel={copy.itinerary} onBack={() => setShowPreferences(false)} />
          ) : (
            <section className="travel-panel" aria-label={copy.itinerary}>
              {showDemoCourse && (
                <div className="guardian-review">
                  <button type="button" disabled={Boolean(pending)} onClick={(event) => recommendCourse(event, true)}>
                    {pending === "recommend" ? copy.loading : "장면 1·2 데모 일정 만들기"}
                  </button>
                  {planError && <p role="alert">{planError}</p>}
                </div>
              )}
              {course?.demo && <small>{plannerCopy.demoCourse}</small>}
              {stops.length ? <PlanList plan={plan} places={places} displayLanguage={language} events={events}
                selected={selected} tripStopId={nextStop?.stop_id} onSelect={selectMode ? toggleChecked : selectStop} lockedLabel={copy.locked}
                checkedIds={selectMode ? checkedIds : undefined}
                formatStopDate={(date) => formatDate(date, language)}
                onSaveStops={selectMode ? undefined : saveStops} busy={Boolean(pending)}
                saveError={scheduleSaveFailed ? plannerCopy.requestFailed : undefined}
                renderStopChecks={liveCourse && !selectMode ? renderStopChecks : undefined}
                onToggleLock={selectMode ? undefined : toggleStopLock} lockCopy={copy.stopLock} /> : <EmptyState message={copy.empty} />}
              {course?.lodging_unavailable && <p>{plannerCopy.lodgingUnavailable}</p>}
              {course?.limited_places && <p>{plannerCopy.limitedPlaces}</p>}
              {course?.unmatched_activities?.length > 0 && (
                <div className="activity-unmatched" role="status">
                  <p>{plannerCopy.activityCopy.unmatched}</p>
                  <ul>{course.unmatched_activities.map((activity) => <li key={activity}>{activity}</li>)}</ul>
                </div>
              )}
              {liveCourse && (
                <section className="guardian-review" aria-label={copy.guardian.check}>
                  <button type="button" disabled={Boolean(pending) || guardianLoading}
                    onClick={() => {
                      manualGuardianCheck.current = { plan, demo };
                      setGuardianActionError(false);
                      setGuardianRefresh((count) => count + 1);
                    }}>
                    {guardianLoading ? copy.loading : copy.guardian.check}
                  </button>
                  {undoRepair?.applied === plan && <button type="button" disabled={Boolean(pending)} onClick={undoGuardianRepair}>{copy.guardian.undo}</button>}
                  {(guardian?.error || (guardianActionError && !alternative && !showDelay)) && <p role="alert">{plannerCopy.requestFailed}</p>}
                  {guardian?.issues?.length === 0 && <p role="status">{copy.guardian.clear}</p>}
                  {guardian?.plan === plan && guardian.manual && guardian.issues.length > 0 && (
                    <ul className="guardian-check-results">
                      {guardian.issues.map((issue) => {
                        const target = stops.find((stop) => stop.stop_id === issue.stop_id);
                        const name = target && resolvePlaceName(target, placesById, language).name;
                        const label = issue.type === "crowded" ? copy.guardian.crowdingWarning : copy.guardian.warning;
                        return <li key={issue.issue_id}>
                          <button type="button" aria-haspopup="dialog" disabled={Boolean(pending)}
                            aria-description={target && formatTime(target.start) + " – " + formatTime(target.end)} onClick={() => {
                            setGuardianActionError(false);
                            setAlternative(issueAlternative(guardian, plan, demo, issue, target));
                          }}>
                            {[name, label, copy.guardian.options].filter(Boolean).join(" · ")}
                          </button>
                        </li>;
                      })}
                    </ul>
                  )}
                </section>
              )}
            </section>
          ))}
        </div>
        {!showTranslation && showChat && chipStops.length > 0 && (
          <ul className="mention-chips" aria-label={selectCopy.mentionLabel}>
            {chipStops.map((stop) => {
              const name = resolvePlaceName(stop, placesById, language).name;
              return <li key={stop.stop_id}>
                <span>@{name}</span>
                <button type="button" aria-label={selectCopy.removeMention(name)} onClick={() => {
                  if (stop === editStop) {
                    setEditId(null);
                    setReviewStatus(null);
                  } else setMentionIds((current) => current.filter((id) => id !== stop.stop_id));
                }}>×</button>
              </li>;
            })}
          </ul>
        )}
        <form className="chat-compose" hidden={showTranslation || !showChat} onSubmit={submit}>
          <div className="chat-input-group">
            {voice.phase && <p className="chat-voice-status" role="status">
              {voice.partial || (voice.phase === "listening" ? translationCopy.listening : translationCopy.working)}
            </p>}
            {voice.error && <p className="chat-voice-status" role="alert">{translationCopy[voice.error]}</p>}
            <textarea ref={composer} aria-label={copy.messageLabel} placeholder={copy.placeholder} rows={1}
              value={draft} maxLength={1000} readOnly={Boolean(voice.phase)} onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
              }} />
          </div>
          {voiceAvailable && (
            <button type="button" className="chat-voice-button" aria-label={voice.phase ? translationCopy.stop : translationCopy.mic}
              aria-pressed={Boolean(voice.phase)} disabled={Boolean(pending) || voice.phase === "finishing" || editStop?.locked}
              onClick={() => voice.toggle(draft)}>
              {voice.phase ? <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1" /></svg> : <MicIcon />}
            </button>
          )}
          <button type="submit" aria-label={copy.send} disabled={!draft.trim() || Boolean(voice.phase) || editStop?.locked || Boolean(pending)}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6" /></svg>
          </button>
        </form>
        {!showTranslation && !showChat && !showPreferences && (
          selectMode && stops.length > 0 ? (
          <div className="trip-actions select-actions" data-has-stops="true">
            <p className="select-actions__count" role="status">{checkedStops.length ? selectCopy.count(checkedStops.length) : selectCopy.none}
              {checkedStops.some((stop) => stop.locked) && <small>{selectCopy.lockedKept}</small>}</p>
            <button type="button" disabled={Boolean(pending) || !checkedStops.some((stop) => !stop.locked)} onClick={deleteChecked}>
              {selectCopy.remove}
            </button>
            <button type="button" disabled={Boolean(pending) || !checkedStops.length} onClick={mentionChecked}>
              {selectCopy.mention}
            </button>
          </div>
          ) : (
          <div className="trip-actions" data-has-stops={stops.length > 0}>
            <button type="button" disabled={Boolean(pending)} onClick={() => setShowPreferences(true)}>
              {stops.length ? plannerCopy.newCourse : plannerCopy.recommend}
            </button>
            {stops.length > 0 && (
              <button type="button" disabled={Boolean(pending)} onClick={toggleTrip}>
                {tripStarted ? copy.endTrip : copy.startTrip}
              </button>
            )}
          </div>
          )
        )}
      </aside>
      {showReset && (
        <TravelActionDialog title={copy.resetItinerary.title}
          className="itinerary-reset-dialog" onClose={() => setShowReset(false)}>
          <p>{copy.resetItinerary.description}</p>
          <div className="stop-time-actions">
            <button type="button" onClick={() => setShowReset(false)} autoFocus>{copy.resetItinerary.cancel}</button>
            <button type="button" className="itinerary-reset-confirm" onClick={resetItinerary}>{copy.resetItinerary.confirm}</button>
          </div>
        </TravelActionDialog>
      )}
      {alternative && alternative.plan === plan && alternative.demo === demo && (
        <GuardianAlternatives alternative={alternative} copy={copy.guardian} placeCopy={plannerCopy.placeCards} language={language} events={events}
          placesById={buildPlacesById([...places, ...alternative.places])} busy={Boolean(pending)}
          error={guardianActionError ? plannerCopy.requestFailed : undefined}
          onApply={applyRepair} onClose={() => setAlternative(null)} />
      )}
      {showDelay && (
        <TravelActionDialog title={copy.guardian.late} closeLabel={copy.guardian.delayClose} className="travel-delay-dialog"
          busy={Boolean(pending)} onClose={() => setShowDelay(false)}>
          <DelayForm copy={copy.guardian} language={language} busy={Boolean(pending)} loadingLabel={copy.loading}
            requestError={guardianActionError ? plannerCopy.requestFailed : undefined} onRequest={requestDelay} />
        </TravelActionDialog>
      )}
      {showLocalCard && (
        <TravelActionDialog title={localCardCopy.listTitle} closeLabel={localCardCopy.close} className="travel-phrases-dialog"
          onClose={() => setShowLocalCard(false)}>
          <LocalCardPicker language={language} hideTitle />
        </TravelActionDialog>
      )}
      <nav ref={tabBar} className="travel-tabs" data-active-tab={tab} aria-label={copy.navigation} inert={regionDraft !== null}>
        <span className="travel-tab-indicator" aria-hidden="true" />
        {Object.entries(tabIcons).map(([name, path]) => (
          <button key={name} data-tab={name} ref={name === "translation" ? translationTrigger : undefined}
            type="button" aria-label={labels[name]} title={labels[name]}
            aria-current={tab === name ? "page" : undefined}
            aria-controls={name === "translation" ? (translationMenu ? "translation-method-popover" : showTranslation ? "travel-chat" : undefined) : name === "chat" || name === "itinerary" ? "travel-chat" : undefined}
            aria-expanded={name === "translation" ? translationMenu || showTranslation : name === "chat" || name === "itinerary" ? tab === name : undefined}
            onClick={() => {
              if (name === "translation") {
                navigatePage("map");
                setOpen(false);
                setExpanded(false);
                setTranslationMode(null);
                setTranslationExpanded(false);
                setMapDetail(null);
                setTranslationMenu(!translationMenu);
                return;
              }
              setTranslationMenu(false);
              setTranslationMode(null);
              if (name !== "home") setMapDetail(null);
              if (name === "profile") {
                setOpen(false);
                setExpanded(false);
                navigatePage(name);
                return;
              }
              navigatePage("map");
              // 넓은 화면: 홈 = 사이드바 접고 지도 전체 보기, 다른 탭 = 사이드바 펼치기
              setSidebarCollapsed(name === "home");
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
        {translationMenu && (
          <div ref={translationPopover} id="translation-method-popover" className="translation-method-popover" role="group" aria-label={translationCopy.title}>
            <button type="button" onClick={() => openTranslation("text")}><TextActionIcon />{translationCopy.text}</button>
            <button type="button" onClick={() => openTranslation("photo")}><PhotoActionIcon camera />{translationCopy.photo}</button>
            <button type="button" onClick={() => openTranslation("voice")}><MicIcon />{translationCopy.voice}</button>
          </div>
        )}
      </nav>
    </main>
  );
}
