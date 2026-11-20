import { PlanClientError, requestJson } from "./planClient.js";

export async function fetchMapEvents(date, signal) {
  const result = await requestJson("/events?" + new URLSearchParams({ date }), { signal });
  if (result?.date !== date || !Array.isArray(result.events)) {
    throw new PlanClientError("invalid_response");
  }
  return result.events;
}

export function mapEventName(event, language) {
  return event.names?.[language]?.trim() || event.names?.ko || event.name;
}
