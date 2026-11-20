const STORE = "entries";

function openAlbum() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("busannow-trip-album", 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE, { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function transaction(mode, access) {
  const database = await openAlbum();
  try {
    return await new Promise((resolve, reject) => {
      const tx = database.transaction(STORE, mode);
      const request = access(tx.objectStore(STORE));
      tx.oncomplete = () => resolve(request.result);
      tx.onabort = () => reject(tx.error);
    });
  } finally {
    database.close();
  }
}

export function saveAlbumEntry(entry) {
  return transaction("readwrite", (store) => store.put(entry));
}

export async function loadAlbum(demoMode) {
  const entries = await transaction("readonly", (store) => store.getAll());
  return entries.filter((entry) => entry.demo === demoMode).sort((a, b) => b.savedAt - a.savedAt);
}

export function saveCompletedTrip(course, demo) {
  return saveAlbumEntry({
    id: "trip-" + crypto.randomUUID(),
    kind: "trip",
    demo,
    savedAt: Date.now(),
    date: course.plan.date ?? course.plan.stops[0].start.slice(0, 10),
    stops: course.plan.stops,
    places: course.places,
    walkingRoute: course.walkingRoute,
  });
}
