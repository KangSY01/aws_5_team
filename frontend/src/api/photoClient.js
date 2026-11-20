import { hasConfiguredPlanApi, PlanClientError, requestJson } from "./planClient.js";

export const photoTypes = ["image/jpeg", "image/png"];
export const photoLanguages = ["en", "ja", "zh-Hans", "zh-Hant"];
const requestTimeout = 60_000;

async function post(path, data, signal, timeoutMs) {
  try {
    return await requestJson(path, {
      signal, timeoutMs,
      request: { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) },
    });
  } catch (error) {
    if (error instanceof PlanClientError) {
      if (error.status === 404) throw new Error("photoMissing");
      if (error.status === 422) throw new Error("photoInvalid");
      if (error.status >= 500) throw new Error("photoServerError");
      if (error.kind === "timeout") throw new Error("photoTimeout");
    }
    throw error;
  }
}

export async function translatePhoto(file, language, signal) {
  if (!photoTypes.includes(file.type) || !photoLanguages.includes(language)) throw new Error("photoInvalid");
  if (!hasConfiguredPlanApi()) throw new Error("unavailable");
  const { upload_url: uploadUrl, key } = await post("/photo/upload-url", { content_type: file.type }, signal);
  if (typeof key !== "string" || !key || typeof uploadUrl !== "string" || !/^https:\/\//i.test(uploadUrl)) {
    throw new Error("failed");
  }
  try {
    const upload = await fetch(uploadUrl, {
      method: "PUT",
      headers: { "Content-Type": file.type },
      body: file,
      signal: AbortSignal.any([signal, AbortSignal.timeout(requestTimeout)]),
    });
    if (!upload.ok) throw new Error("photoUploadFailed");
  } catch (error) {
    if (signal.aborted) throw error;
    throw new Error("photoUploadFailed");
  }
  const translation = await post("/photo/translate", { key, language }, signal, requestTimeout);
  const items = translation?.items;
  if (translation?.key !== key || translation?.language !== language || !Array.isArray(items) ||
      !items.every((item) => item && typeof item.text_ko === "string" && typeof item.translated === "string" &&
        (item.spicy === null || typeof item.spicy === "boolean") &&
        ["left", "top", "width", "height"].every((field) => {
          const value = item.bbox?.[field];
          return Number.isFinite(value) && value >= 0 && value <= 1;
        }))) throw new Error("failed");
  return items;
}
