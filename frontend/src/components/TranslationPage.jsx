import { useEffect, useRef, useState } from "react";
import { languages } from "../constants/travelCopy.js";
import { detectSourceLanguage, translateText } from "../api/translationClient.js";
import { photoLanguages, photoTypes, translatePhoto } from "../api/photoClient.js";
import { localeFlags } from "../constants/localeFlags.js";
import "./translation-page.css";

const speechLocales = { ko: "ko-KR", en: "en-US", ja: "ja-JP", "zh-Hans": "zh-CN", "zh-Hant": "zh-TW" };

const photoTargetKey = "busannow.photoTranslationTarget";

function loadPhotoTarget() {
  try {
    const value = window.localStorage.getItem(photoTargetKey);
    return photoLanguages.includes(value) ? value : null;
  } catch {
    return null;
  }
}

export default function TranslationPage({ mode, active, language, copy, onInputFocus }) {
  const [speechLanguage, setSpeechLanguage] = useState("ko");
  const [voiceSource, setVoiceSource] = useState("");
  const [spokenSource, setSpokenSource] = useState("");
  const [resolvedVoiceSource, setResolvedVoiceSource] = useState("");
  const [editVoiceSource, setEditVoiceSource] = useState(false);
  const [targetChoice, setTarget] = useState(null);
  const [photoTarget, setPhotoTarget] = useState(loadPhotoTarget);
  const [photoItems, setPhotoItems] = useState([]);
  const defaultTarget = language !== "ko" && Object.hasOwn(languages, language) ? language : "en";
  const isPhoto = mode === "photo";
  const isVoice = mode === "voice";
  const isText = mode === "text";
  const [hasTranscript, setHasTranscript] = useState(false);
  const target = (isPhoto ? photoTarget : targetChoice) ?? defaultTarget;
  const [draft, setDraft] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [speechStarting, setSpeechStarting] = useState(false);
  const speechActive = listening || speechStarting;
  const [message, setMessage] = useState("");
  const [result, setResult] = useState("");
  const body = useRef(null);
  const recognition = useRef(null);
  const pending = useRef(null);

  useEffect(() => {
    return () => {
      const current = recognition.current;
      recognition.current = null;
      current?.abort();
      pending.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!file) { setPreview(""); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    if (active) return;
    const current = recognition.current;
    recognition.current = null;
    current?.abort();
    setListening(false);
    setSpeechStarting(false);
    pending.current?.abort();
    pending.current = null;
    setBusy(false);
  }, [active]);

  function clearResult() {
    setMessage("");
    setPhotoItems([]);
    setResult("");
  }

  function stopSpeech() {
    const current = recognition.current;
    recognition.current = null;
    current?.abort();
    setListening(false);
    setSpeechStarting(false);
  }

  function startSpeech() {
    if (recognition.current || busy) return;
    clearResult();
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) { setMessage("micUnsupported"); return; }
    const session = new SpeechRecognition();
    recognition.current = session;
    session.lang = speechLocales[speechLanguage];
    session.interimResults = false;
    session.onstart = () => {
      if (recognition.current !== session) return;
      setSpeechStarting(false);
      setListening(true);
    };
    session.onresult = (event) => {
      if (recognition.current !== session) return;
      setDraft(event.results[0][0].transcript);
      setHasTranscript(true);
      setSpokenSource(speechLanguage);
      setVoiceSource("");
      setResolvedVoiceSource("");
      setEditVoiceSource(false);
    };
    session.onerror = ({ error }) => {
      if (recognition.current !== session) return;
      setMessage(["not-allowed", "service-not-allowed", "audio-capture"].includes(error) ? "micDenied" : "micError");
    };
    session.onend = () => {
      if (recognition.current !== session) return;
      recognition.current = null;
      setListening(false);
      setSpeechStarting(false);
    };
    try {
      setSpeechStarting(true);
      session.start();
    } catch {
      stopSpeech();
      setMessage("micError");
    }
  }

  function updateDraft(value) {
    clearResult();
    setDraft(value);
    setSpokenSource("");
    setResolvedVoiceSource("");
  }

  function chooseFile(event) {
    const image = event.target.files?.[0];
    event.target.value = "";
    if (!image) return;
    clearResult();
    if (!photoTypes.includes(image.type)) {
      setFile(null);
      setMessage("photoInvalid");
      return;
    }
    setFile(image);
  }

  function changePhotoTarget(value) {
    clearResult();
    setPhotoTarget(value);
    try {
      window.localStorage.setItem(photoTargetKey, value);
    } catch {
      // Keep the selection for this session if storage is unavailable.
    }
  }

  function submit(event) {
    event.preventDefault();
    void runTranslation(file);
  }

  function handlePreviewError() {
    pending.current?.abort();
    pending.current = null;
    setBusy(false);
    clearResult();
    setFile(null);
    setMessage("imageError");
  }

  async function runTranslation(image) {
    if (pending.current || speechActive || (!isPhoto && !draft.trim())) return;
    if (isPhoto && !image) return;
    const request = new AbortController();
    pending.current = request;
    clearResult();
    setBusy(true);
    try {
      if (isPhoto) {
        const items = await translatePhoto(image, target, request.signal);
        if (request.signal.aborted) return;
        setPhotoItems(items);
        if (!items.length) setMessage("noText");
        return;
      }
      const text = draft.trim();
      const from = voiceSource || spokenSource || await detectSourceLanguage(text, request.signal);
      if (request.signal.aborted) return;
      if (!from) {
        setEditVoiceSource(true);
        setMessage("detectVoiceFailed");
        return;
      }
      setResolvedVoiceSource(from);
      const translated = from === target ? text : await translateText(text, from, target, request.signal);
      if (!request.signal.aborted) setResult(translated);
    } catch (error) {
      if (!request.signal.aborted) setMessage(Object.hasOwn(copy, error.message) ? error.message : "failed");
    } finally {
      if (!request.signal.aborted) {
        pending.current = null;
        setBusy(false);
      }
    }
  }

  const emptyPhoto = mode === "photo" && !file;
  const emptyText = !isPhoto && !draft.trim();
  const compact = active && (emptyPhoto || (isVoice && emptyText));
  useEffect(() => {
    if (!compact) return;
    const form = body.current;
    const sheet = form.closest(".travel-chat");
    const app = sheet.closest(".travel-preview");
    const parts = [sheet.querySelector(".chat-grab"), sheet.querySelector(".chat-heading"), form.querySelector("fieldset")];
    function measure() {
      const style = getComputedStyle(form);
      const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
      const height = parts.reduce((sum, part) => sum + part.getBoundingClientRect().height, padding);
      app.style.setProperty("--compact-translation-height", Math.ceil(height) + "px");
    }
    const observer = new ResizeObserver(measure);
    parts.forEach((part) => observer.observe(part));
    measure();
    return () => {
      observer.disconnect();
      app.style.removeProperty("--compact-translation-height");
    };
  }, [compact]);


  const inputHelp = message ? copy[message] : listening ? copy.listening : (busy || speechStarting) ? copy.working
    : emptyPhoto && copy.photoNeeded;

  return (
    <div className="translation-page" hidden={!active} data-compact-translation={compact}>
      <form className="chat-content translation-body" id={mode + "-translation-form"} ref={body} onSubmit={submit}>
          <fieldset disabled={busy}>
            <div className={isText ? "translation-language-pair translation-text-pair" : isVoice ? "translation-language-pair" : undefined}>
              {isText && <LanguageField label={copy.source} value={voiceSource} placeholder={copy.autoDetect} allowAuto
                onChange={(value) => { clearResult(); setVoiceSource(value); }} />}
              {isVoice && <LanguageField label={copy.speakingLanguage} value={speechLanguage} onChange={setSpeechLanguage} disabled={speechActive} />}
              {!isPhoto && <DirectionIcon />}
              <LanguageField label={copy.photoTarget} value={target} available={isPhoto ? photoLanguages : undefined} onChange={isPhoto ? changePhotoTarget : (value) => {
                clearResult();
                setTarget(value);
              }} />
              {isText && (
                <>
                  <textarea className="translation-text-source" aria-label={copy.input} placeholder={copy.input} rows={3}
                    value={draft} onFocus={onInputFocus} onChange={(event) => updateDraft(event.target.value)} />
                  <div className="translation-text-result" role="status" aria-label={copy.result}>
                    {result ? <span lang={target}>{result}</span> : <span className="translation-result-placeholder">{copy.resultPlaceholder}</span>}
                  </div>
                </>
              )}
            </div>
            {isPhoto ? (
              <>
                <div className="translation-photo-inputs">
                  <label><PhotoActionIcon camera /><span>{copy.camera}</span><input type="file" accept="image/jpeg,image/png" capture="environment" onChange={chooseFile} /></label>
                  <label><PhotoActionIcon /><span>{copy.upload}</span><input type="file" accept="image/jpeg,image/png" onChange={chooseFile} /></label>
                </div>
                {preview && (
                  <div className="translation-image">
                    <img className="translation-preview" src={preview} alt={copy.preview} onError={handlePreviewError} />
                    <div className="translation-image-overlay" aria-hidden="true">
                      {photoItems.map(({ bbox, translated }, index) => (
                        <span key={index} lang={target} style={{
                          left: `${bbox.left * 100}%`, top: `${bbox.top * 100}%`,
                          width: `${Math.min(bbox.width, 1 - bbox.left) * 100}%`,
                          height: `${Math.min(bbox.height, 1 - bbox.top) * 100}%`,
                        }}>{translated}</span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : isVoice && (
              <>
                {isVoice && (
                  <div className="translation-microphone">
                    <button type="button" aria-label={speechActive ? copy.stop : copy.mic}
                      onClick={speechStarting ? stopSpeech : listening ? () => recognition.current?.stop() : startSpeech}>
                      {speechActive ? copy.stop : <MicIcon />}
                    </button>
                  </div>
                )}
                {(!isVoice || hasTranscript) && (
                  <div className="translation-voice-input">
                    <textarea aria-label={copy.input} placeholder={copy.input} rows={3} value={draft} onFocus={onInputFocus}
                      onChange={(event) => updateDraft(event.target.value)} />
                  </div>
                )}
                <div className="translation-voice-result" role="status">
                  {result && (
                    <section className="translation-result" aria-labelledby={mode + "-translation-result-title"}>
                      <h2 id={mode + "-translation-result-title"}>{copy.result} · <span lang={target}>{languages[target]}</span></h2>
                      <p lang={target}>{result}</p>
                    </section>
                  )}
                </div>
                {!emptyText && (editVoiceSource ? (
                  <LanguageField label={copy.source} value={voiceSource || resolvedVoiceSource} placeholder={copy.chooseSource} onChange={(value) => {
                    clearResult();
                    setVoiceSource(value);
                  }} />
                ) : result && (
                  <button type="button" className="translation-swap" onClick={() => setEditVoiceSource(true)}>{copy.correctSource}</button>
                ))}
              </>
            )}
            {inputHelp && <p id={mode + "-translation-help"} className="translation-help" role="status">{inputHelp}</p>}
        </fieldset>
        {isPhoto && photoItems.length > 0 && (
          <section className="translation-status" role="status" aria-label={copy.result}>
            <h2>{copy.result}</h2>
            <ul className="translation-photo-results">
              {photoItems.map(({ text_ko, translated, spicy }, index) => (
                <li key={index}>
                  <span lang="ko">{text_ko}</span>
                  <strong lang={target}>{translated}</strong>
                  <small>{spicy === null ? copy.spicyUnknown : spicy ? copy.spicyYes : copy.spicyNo}</small>
                </li>
              ))}
            </ul>
          </section>
        )}
      </form>
      <div className="translation-footer" hidden={isPhoto ? emptyPhoto : isVoice && emptyText}>
        <button aria-describedby={inputHelp ? mode + "-translation-help" : undefined} form={mode + "-translation-form"} className="translation-submit" type="submit" disabled={busy || speechActive || (isPhoto ? !file : emptyText || (isVoice && editVoiceSource && !voiceSource && !resolvedVoiceSource))}>
              {busy ? copy.working : mode === "photo" ? copy.photoSubmit : copy.submit}
            </button>
      </div>
    </div>
  );
}

const flagEmoji = { ko: "🇰🇷", en: "🇬🇧", ja: "🇯🇵", "zh-Hans": "🇨🇳", "zh-Hant": "🇹🇼" };

function LanguageValue({ value, placeholder }) {
  return (
    <span className="translation-language-value" aria-hidden="true">
      {value && <img src={localeFlags[value]} alt="" width="16" height="16" />}
      <span lang={value || undefined}>{languages[value] || placeholder}</span>
    </span>
  );
}

function LanguageField({ label, value, onChange, placeholder, disabled, allowAuto, available = Object.keys(languages) }) {
  return (
    <label className="translation-photo-field">
      <span className="translation-language-label">{label}</span>
      <span className="translation-select">
        <LanguageValue value={value} placeholder={placeholder} />
        <select aria-label={label} disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)}>
          {placeholder && <option value="" disabled={!allowAuto}>{placeholder}</option>}
          {available.map((code) => <option key={code} value={code} lang={code}>{flagEmoji[code]} {languages[code]}</option>)}
        </select>
      </span>
    </label>
  );
}

function DirectionIcon() {
  return (
    <span className="translation-direction" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 12h16m-6-6 6 6-6 6" />
      </svg>
    </span>
  );
}

export function PhotoActionIcon({ camera = false }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {camera ? (
        <>
          <path d="M4 7h4l2-3h4l2 3h4a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1Z" />
          <circle cx="12" cy="13" r="3" />
        </>
      ) : <path d="M12 16V4m-4 4 4-4 4 4M4 16v4h16v-4" />}
    </svg>
  );
}

export function MicIcon() {
  return <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" aria-hidden="true">
    <rect x="9" y="3" width="6" height="12" rx="3" />
    <path d="M5 11v1a7 7 0 0 0 14 0v-1m-7 8v3m-3 0h6" />
  </svg>;
}

export function TextActionIcon() {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" aria-hidden="true">
    <path d="M5 6h14M12 6v13m-3 0h6M5 6v3m14-3v3" />
  </svg>;
}
