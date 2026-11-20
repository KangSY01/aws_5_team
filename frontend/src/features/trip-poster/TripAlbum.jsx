import { useEffect, useRef, useState } from "react";
import TravelActionDialog from "../../components/TravelActionDialog.jsx";
import { loadAlbum, saveAlbumEntry } from "./album.js";
import "./trip-poster.css";

const text = {
  ko: ["여행 앨범", "여행을 종료하면 이곳에 기록이 저장돼요.", "부산네컷 만들기", "닫기", "사진 추가 (최대 4장)", "포스터를 만드는 중…", "앨범에 저장", "PNG 저장", "공유", "포스터를 만들거나 저장하지 못했어요. 다시 시도해 주세요.", "다시 시도"],
  en: ["Trip album", "Completed trips are saved here.", "Make Busan in Four Frames", "Close", "Add photos (up to 4)", "Making your poster…", "Save to album", "Download PNG", "Share", "Couldn’t create or save the poster. Please try again.", "Try again"],
  ja: ["旅のアルバム", "旅行を終了すると、ここに記録されます。", "釜山フォトポスターを作る", "閉じる", "写真を追加（最大4枚）", "ポスターを作成中…", "アルバムに保存", "PNGを保存", "共有", "ポスターを作成または保存できませんでした。もう一度お試しください。", "再試行"],
  "zh-Hans": ["旅行相册", "旅行结束后，记录会保存在这里。", "制作釜山四格海报", "关闭", "添加照片（最多4张）", "正在制作海报…", "保存到相册", "下载 PNG", "分享", "无法制作或保存海报，请重试。", "重试"],
  "zh-Hant": ["旅行相簿", "旅行結束後，紀錄會儲存在這裡。", "製作釜山四格海報", "關閉", "加入照片（最多4張）", "正在製作海報…", "儲存到相簿", "下載 PNG", "分享", "無法製作或儲存海報，請重試。", "重試"],
};

const photoCopy = { ko: "사진", en: "Photos", ja: "写真", "zh-Hans": "照片", "zh-Hant": "照片" };

function useImageUrl(blob) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!blob) {
      setUrl("");
      return;
    }
    const next = URL.createObjectURL(blob);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [blob]);
  return url;
}

function download(png, date) {
  const url = URL.createObjectURL(png);
  const link = document.createElement("a");
  link.href = url;
  link.download = "BusanNow-" + date + ".png";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function AlbumThumbnail({ entry, onOpen }) {
  const url = useImageUrl(entry.png);
  return <button className="album-thumbnail" type="button" onClick={onOpen}>
    {url && <img src={url} alt="부산네컷" />}
    <span>{entry.date}</span>
  </button>;
}

function PhotoSlot({ file, index, add, photo, onAdd }) {
  const src = useImageUrl(file);
  const number = index + 1;
  return file ? (
    <div className="poster-photo-slot">{src && <img src={src} alt={photo + " " + number} />}</div>
  ) : (
    <button type="button" className="poster-photo-slot" aria-label={add + " " + number} onClick={onAdd}>
      <span className="poster-photo-plus" aria-hidden="true">+</span>
    </button>
  );
}

function PosterDialog({ entry, language, labels, onClose, onSaved }) {
  const { make, close, add, creating, save, pngLabel, share, error, retry } = labels;
  const [photos, setPhotos] = useState([]);
  const addInput = useRef(null);
  const photoLabel = photoCopy[language];
  const [rendered, setRendered] = useState(null);
  const [revision, setRevision] = useState(0);
  const [renderError, setRenderError] = useState(false);
  const [actionError, setActionError] = useState(false);
  const [busy, setBusy] = useState(false);
  const alive = useRef(false);
  const mapCache = useRef(new Map());
  const png = entry.png ?? (rendered?.photos === photos && rendered?.revision === revision ? rendered.png : null);
  const url = useImageUrl(png ?? rendered?.png);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  useEffect(() => {
    if (entry.png) return;
    const request = new AbortController();
    setRenderError(false);
    setActionError(false);
    const timer = setTimeout(async () => {
      try {
        const { createPoster } = await import("./renderPoster.js");
        if (request.signal.aborted) return;
        const output = await createPoster(entry, photos, language, request.signal, mapCache.current);
        if (!request.signal.aborted) setRendered({ photos, revision, png: output });
      } catch {
        if (!request.signal.aborted) setRenderError(true);
      }
    }, 80);
    return () => {
      clearTimeout(timer);
      request.abort();
    };
  }, [entry, language, photos, revision]);

  function selectPhotos(event) {
    const files = Array.from(event.currentTarget.files ?? []);
    event.currentTarget.value = "";
    if (files.length) setPhotos((current) => [...current, ...files].slice(0, 4));
  }

  async function savePoster() {
    if (photos.length !== 4 || !png || busy) return;
    setBusy(true);
    setActionError(false);
    const poster = {
      id: "poster-" + crypto.randomUUID(), kind: "poster", demo: entry.demo,
      savedAt: Date.now(), date: entry.date, png,
    };
    try {
      await saveAlbumEntry(poster);
      onSaved(poster);
    } catch {
      if (alive.current) setActionError(true);
    } finally {
      if (alive.current) setBusy(false);
    }
  }

  const shareFile = entry.png && typeof File === "function" ? new File([entry.png], "BusanNow-" + entry.date + ".png", { type: "image/png" }) : null;
  const canShare = shareFile && navigator.share && navigator.canShare?.({ files: [shareFile] });

  async function sharePoster() {
    try {
      await navigator.share({ files: [shareFile], title: "부산네컷" });
    } catch (failure) {
      if (failure.name !== "AbortError") setActionError(true);
    }
  }

  return (
    <TravelActionDialog className="trip-poster-dialog" title={entry.png ? "부산네컷" : make} closeLabel={close} onClose={onClose} busy={busy}>
      <div className="trip-poster-body">
        <div className="trip-poster-preview">
          {url && <img src={url} alt="부산네컷" />}
          {!png && <div className="trip-poster-render-status">
            {renderError ? <><p role="alert">{error}</p><button type="button" onClick={() => setRevision((value) => value + 1)}>{retry}</button></>
              : <p role="status">{creating}</p>}
          </div>}
        </div>
        {!entry.png && (
          <section className="trip-poster-photos" aria-label={photoLabel}>
            <h3>{photoLabel} {photos.length}/4</h3>
            <input ref={addInput} type="file" accept="image/*" multiple hidden onChange={selectPhotos} />
            <div className="poster-photo-grid">
              {Array.from({ length: 4 }, (_, index) => (
                <PhotoSlot key={index} index={index} file={photos[index]} add={add} photo={photoLabel}
                  onAdd={() => addInput.current.click()} />
              ))}
            </div>
          </section>
        )}
      </div>
      <footer className="trip-poster-actions">
        {actionError && <p role="alert">{error}</p>}
        {!entry.png ? (
          <button className="trip-poster-primary" type="button" disabled={photos.length !== 4 || !png || busy} onClick={savePoster}>{save}</button>
        ) : <div className="trip-poster-secondary">
          <button type="button" disabled={!png} onClick={() => download(png, entry.date)}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12m-4-4 4 4 4-4M5 16v5h14v-5" /></svg>
            {pngLabel}
          </button>
          <button type="button" disabled={!canShare} onClick={sharePoster}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V3m-4 4 4-4 4 4M8 11H5v10h14V11h-3" /></svg>
            {share}
          </button>
        </div>}
      </footer>
    </TravelActionDialog>
  );
}

export default function TripAlbum({ language, demoMode, revision, archiveError }) {
  const [entries, setEntries] = useState([]);
  const [opened, setOpened] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [album, empty, make, close, add, creating, save, pngLabel, share, error, retry] = text[language];
  const labels = { make, close, add, creating, save, pngLabel, share, error, retry };

  useEffect(() => {
    let disposed = false;
    loadAlbum(demoMode).then((results) => {
      if (!disposed) setEntries(results);
    }).catch(() => {
      if (!disposed) setLoadError(true);
    }).finally(() => {
      if (!disposed) setLoaded(true);
    });
    return () => { disposed = true; };
  }, [demoMode, revision]);

  return (
    <section className="trip-album">
      <h2>{album}</h2>
      {(archiveError || loadError) && <p role="alert">{error}</p>}
      {loaded && !loadError && !entries.length && <p>{empty}</p>}
      <div className="trip-album-grid">
        {entries.filter(({ kind }) => kind === "poster").map((entry) =>
          <AlbumThumbnail key={entry.id} entry={entry} onOpen={() => setOpened(entry)} />)}
      </div>
      {entries.filter(({ kind }) => kind === "trip").map((entry) => (
        <div className="trip-album-record" key={entry.id}>
          <time dateTime={entry.date}>{entry.date}</time>
          <button type="button" onClick={() => setOpened(entry)}>{make}</button>
        </div>
      ))}
      {opened && <PosterDialog key={opened.id} entry={opened} language={language} labels={labels}
        onClose={() => setOpened(null)} onSaved={(poster) => {
          setEntries((current) => [poster, ...current]);
          setOpened(null);
        }} />}
    </section>
  );
}
