const ocrLanguages = { ko: "kor", en: "eng", ja: "jpn", "zh-Hans": "chi_sim", "zh-Hant": "chi_tra" };

export async function readPhoto(file, language) {
  const { createWorker } = await import("tesseract.js");
  const worker = await createWorker(language ? ocrLanguages[language] : Object.values(ocrLanguages));
  try {
    const { data } = await worker.recognize(file);
    return data.text.trim();
  } finally {
    await worker.terminate();
  }
}

function detectWrittenLanguage(text) {
  const korean = /\p{Script=Hangul}/u.test(text);
  const japanese = /[\p{Script=Hiragana}\p{Script=Katakana}]/u.test(text);
  if (korean && japanese) return null;
  if (korean) return "ko";
  if (japanese) return "ja";
  if (/\p{Script=Han}/u.test(text)) return null;
  if (/^[\p{Script=Latin}\p{Number}\p{Punctuation}\p{Separator}\s]+$/u.test(text)
    && /\b(the|and|with|please|menu|coffee|opening|hours|welcome|fresh|entrance|exit)\b/i.test(text)) return "en";
  return null;
}

export async function detectSourceLanguage(text, signal) {
  const inferred = detectWrittenLanguage(text);
  const api = globalThis.LanguageDetector;
  if (inferred || !text || !api) return inferred;
  try {
    if (await api.availability() === "unavailable") return null;
    const detector = await api.create({ signal });
    try {
      const [best] = await detector.detect(text, { signal });
      const code = best?.detectedLanguage;
      return best?.confidence >= .7 && Object.hasOwn(ocrLanguages, code) ? code : null;
    } finally {
      detector.destroy();
    }
  } catch (error) {
    if (signal.aborted) throw error;
    return null;
  }
}

export async function translateText(text, source, target, signal) {
  const endpoint = import.meta.env.VITE_TRANSLATION_ENDPOINT?.trim();
  if (endpoint) {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ q: text, source, target, format: "text" }),
      signal,
    });
    if (!response.ok) throw new Error("failed");
    const { translatedText } = await response.json();
    if (typeof translatedText !== "string" || !translatedText.trim()) throw new Error("failed");
    return translatedText;
  }

  const api = globalThis.Translator;
  const pair = { sourceLanguage: source, targetLanguage: target };
  if (!api || await api.availability(pair) === "unavailable") throw new Error("unavailable");
  const translator = await api.create({ ...pair, signal });
  try {
    return await translator.translate(text, { signal });
  } finally {
    translator.destroy();
  }
}
